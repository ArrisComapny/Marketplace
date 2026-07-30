import asyncio
import logging
import signal

from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy.exc import OperationalError

from wb_sdk.wb_api import WBApi
from database import WBDbConnection
from wb_sdk.errors import ClientError


LOG_DIR = Path(__file__).resolve().parent / 'log_wbchats'
LOG_DIR.mkdir(exist_ok=True)


class DailyFileHandler(logging.Handler):
    def __init__(self, directory: Path, encoding: str = 'utf-8') -> None:
        super().__init__()
        self.directory = directory
        self.encoding = encoding
        self._current_date: str | None = None
        self._stream = None
        self._roll()

    def _roll(self) -> None:
        today = datetime.now().strftime('%Y-%m-%d')
        if today == self._current_date and self._stream:
            return
        if self._stream:
            self._stream.close()
        self._current_date = today
        self._stream = open(self.directory / f"{today}.log", 'a', encoding=self.encoding)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._roll()
            self._stream.write(self.format(record) + '\n')
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._stream:
            self._stream.close()
            self._stream = None
        super().close()


_formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')

_file_handler = DailyFileHandler(LOG_DIR)
_file_handler.setFormatter(_formatter)

_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _stream_handler])
logger = logging.getLogger(__name__)


async def get_chats(
        db_conn: WBDbConnection, client_id: str, api_key: str, today: datetime,
) -> list[tuple[str, str, int]]:
    list_chats = []
    from_timestamp = int(today.timestamp() * 1000)

    skus = db_conn.get_wb_sku_vendor_code(client_id=client_id, new=False)

    mes = ('Здравствуйте. Вы оставили отзыв с низкой оценкой. '
           'Давайте обсудим, что не так с товаром. '
           'Пожалуйста, расскажите подробно: попробую решить проблему')

    mes2 = ('Здравствуйте. Вы дополнили отзыв и поставили низкую оценку. '
            'Очень хотим разобраться и всё исправить. '
            'Пожалуйста, расскажите подробно: попробую решить проблему')

    api_user = WBApi(api_key=api_key)
    answer_chats = await api_user.get_chats()
    result = answer_chats.result

    if result:
        for row in result:
            if row.lastMessage and row.goodCard:
                message = row.lastMessage.text
                timestamp = row.lastMessage.addTimestamp

                if message in (mes, mes2) and timestamp >= from_timestamp:
                    vendor_code = skus.get(str(row.goodCard.nmID))
                    if vendor_code:
                        list_chats.append((row.replySign, vendor_code, timestamp))

    logger.info(f"Количество чатов для ответа: {len(list_chats)}")
    return list_chats


async def post_chats(api_key: str, chats: list[tuple[str, str, int]]) -> None:
    mes = ('Важное уведомление\n'
           'Предыдущее сообщение было отправлено по ошибке из-за технического сбоя.\n'
           'Просим Вас не отвечать ни на предыдущее сообщение, ни на это уведомление.\n'
           'Все ответы на такие служебные сообщения автоматически отклоняются и не доходят до сотрудников поддержки.\n'
           'Если вы отправите сообщение, оно не будет доставлено оператору поддержки и не поступит на рассмотрение.\n'
           'Пожалуйста, воздержитесь от ответа.')

    api_user = WBApi(api_key=api_key)
    msk = timezone(timedelta(hours=3))

    for chat, vendor_code, timestamp in chats:
        dt = datetime.fromtimestamp(timestamp / 1000, tz=msk)

        logger.info(f"Ответ по отзыву на {vendor_code} за {dt} отправляется")
        answer_chats = await api_user.get_message(reply_sign=chat, message=mes)

        if answer_chats and answer_chats.result:
            logger.info(f"Ответ по отзыву на {vendor_code} за {dt} отправлен")
        elif answer_chats and answer_chats.errors:
            logger.error(f"Ответ не отправлен: {answer_chats.errors}")
        else:
            logger.error("Ответ не отправлен: неизвестная ошибка")


async def process_client(db_conn: WBDbConnection, client) -> None:
    negative_client = db_conn.get_wb_negative(client_id=client.client_id)
    if not negative_client or not negative_client.work:
        return

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        logger.info(f"[{client.name_company}] поиск чатов по негативам")
        chats = await get_chats(
            db_conn=db_conn,
            client_id=client.client_id,
            api_key=client.api_key,
            today=today,
        )
        if chats:
            await post_chats(api_key=negative_client.api_key, chats=chats)
    except ClientError as e:
        logger.error(f'[{client.name_company}] {e}')


async def client_loop(db_conn: WBDbConnection, client, interval_seconds: int) -> None:
    while True:
        try:
            await process_client(db_conn, client)
        except asyncio.CancelledError:
            logger.info(f'[{client.name_company}] остановлен')
            raise
        except Exception:
            logger.exception(f'[{client.name_company}] итерация упала, продолжаем')
        await asyncio.sleep(interval_seconds)


async def supervisor(
    db_conn: WBDbConnection,
    interval_seconds: int = 10,
    refresh_seconds: int = 60,
) -> None:
    tasks: dict[str, asyncio.Task] = {}

    try:
        while True:
            try:
                clients = db_conn.get_clients(marketplace="WB")
                current = {c.client_id: c for c in clients}

                for client_id, client in current.items():
                    task = tasks.get(client_id)
                    if task is None or task.done():
                        if task and task.done():
                            logger.warning(f'[{client.name_company}] таск завершился, перезапуск')
                        else:
                            logger.info(f'[{client.name_company}] старт')
                        tasks[client_id] = asyncio.create_task(
                            client_loop(db_conn, client, interval_seconds),
                            name=f'client-{client_id}',
                        )

                for client_id in list(tasks):
                    if client_id not in current:
                        logger.info(f'Останавливаем кабинет {client_id}')
                        tasks[client_id].cancel()
                        try:
                            await tasks[client_id]
                        except (asyncio.CancelledError, Exception):
                            pass
                        del tasks[client_id]
            except OperationalError:
                logger.error('БД недоступна при опросе клиентов, ждём')
            except Exception:
                logger.exception('Ошибка в супервизоре')

            await asyncio.sleep(refresh_seconds)
    finally:
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)


async def main_wb_chats(interval_seconds: int = 10, refresh_seconds: int = 60) -> None:
    db_conn = WBDbConnection()
    db_conn.start_db()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    sup_task = asyncio.create_task(
        supervisor(db_conn, interval_seconds=interval_seconds, refresh_seconds=refresh_seconds)
    )

    await stop.wait()
    sup_task.cancel()
    try:
        await sup_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main_wb_chats())
