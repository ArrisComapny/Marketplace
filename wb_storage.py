import asyncio
import logging

import nest_asyncio

from datetime import datetime, timedelta

from sqlalchemy.exc import OperationalError

from wb_sdk.errors import ClientError
from wb_sdk.wb_api import WBApi
from database import WBDbConnection
from data_classes import DataWBStorage

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def get_storage(db_conn: WBDbConnection, client_id: str, api_key: str, from_date: str, to_date: str) -> None:
    """
        Получает список расходов по хранению для указанного клиента за определенный период времени.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            from_date (str): Начальная дата периода (В формате строки).
                Формат: YYYY-MM-DDTHH:mm:ss.sssZ.
                Пример: 2019-11-25T10:43:06.51Z.
            to_date (str): Конечная дата периода (В формате строки).
                Формат: YYYY-MM-DDTHH:mm:ss.sssZ.
                Пример: 2019-11-25T10:43:06.51Z.
    """
    def format_date(date_format: str) -> datetime.date:
        """Форматирование даты."""
        time_format = "%Y-%m-%d"
        return datetime.strptime(date_format.split('T')[0], time_format).date()

    list_storage = []

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)

    # Создание отчёта по хранению
    answer = await api_user.get_paid_storage(date_from=from_date, date_to=to_date)

    if answer:
        task_id = answer.data.taskId  # ID отчёта

        # Проверка готовности отчёта
        while True:
            await asyncio.sleep(5)
            answer_status = await api_user.get_paid_storage_status(task_id=task_id)
            if answer_status:
                if answer_status.data.status == 'done':
                    break
                elif answer_status.data.status == 'canceled':
                    logger.info(f"Отчет отменен")
                    return

        # Получение отчёта
        answer_download = await api_user.get_paid_storage_download(task_id=task_id)

        # Обработка полученных результатов
        if answer_download:
            for storage in answer_download.result:
                list_storage.append(DataWBStorage(client_id=client_id,
                                                  date=format_date(storage.date),
                                                  vendor_code=storage.vendorCode,
                                                  sku=str(storage.nmId),
                                                  calc_type=storage.calcType,
                                                  cost=round(float(storage.warehousePrice), 2)))
        else:
            logger.error(f"Ошибка ответа или пустой отчет {answer_download}")

    # Агрегирование данных
    aggregate = {}
    for row in list_storage:
        key = (
            row.client_id,
            row.date,
            row.vendor_code,
            row.sku,
            row.calc_type
        )
        if key in aggregate:
            aggregate[key] += row.cost
        else:
            aggregate[key] = row.cost
    list_storage = []
    for key, cost in aggregate.items():
        client_id, date, vendor_code, sku, calc_type = key
        list_storage.append(DataWBStorage(client_id=client_id,
                                          date=date,
                                          vendor_code=vendor_code,
                                          sku=sku,
                                          calc_type=calc_type,
                                          cost=cost))

    logger.info(f"Количсетво строк: {len(list_storage)}")
    db_conn.add_wb_storage_entry(list_storage=list_storage)


async def main_wb_storage(retries: int = 6) -> None:
    try:
        db_conn = WBDbConnection()

        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="WB")
        date_now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        from_date = date_now - timedelta(days=1)
        to_date = date_now - timedelta(microseconds=1)

        for client in clients:
            try:
                logger.info(f'Сбор информации о хранении маназина {client.name_company} за дату {from_date.date().isoformat()}')
                await get_storage(db_conn=db_conn,
                                  client_id=client.client_id,
                                  api_key=client.api_key,
                                  from_date=from_date.isoformat(),
                                  to_date=to_date.isoformat())
            except ClientError as e:
                logger.error(f'{e}')
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_wb_storage(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_wb_storage())
    loop.stop()
