import asyncio
import logging

import nest_asyncio

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import OperationalError

from wb_sdk.errors import ClientError
from wb_sdk.wb_api import WBApi
from database import WBDbConnection
from data_classes import DataWBSupply

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def get_supplies(db_conn: WBDbConnection, client_id: str, api_key: str,
                       from_date: datetime, to_date: datetime) -> None:
    """
        Получает список поставок FBW для указанного клиента за определенный период времени.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            from_date (datetime): Начальная дата периода (по дате создания поставки).
            to_date (datetime): Конечная дата периода (по дате создания поставки).
    """
    def format_date(date_format: str) -> datetime | None:
        """Форматирование даты."""
        if not date_format:
            return None
        return datetime.fromisoformat(date_format)

    list_supplies = []

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)

    limit = 1000
    offset = 0

    while True:
        # Получение списка поставок
        answer = await api_user.get_supplies(from_date=from_date.date().isoformat(),
                                             to_date=to_date.date().isoformat(),
                                             limit=limit,
                                             offset=offset)

        if not answer or not answer.result:
            break

        # Обработка полученных результатов
        for supply in answer.result:
            list_supplies.append(DataWBSupply(client_id=client_id,
                                              supply_id=str(supply.supplyID) if supply.supplyID else None,
                                              preorder_id=str(supply.preorderID),
                                              phone=supply.phone,
                                              create_date=format_date(supply.createDate),
                                              supply_date=format_date(supply.supplyDate),
                                              fact_date=format_date(supply.factDate),
                                              updated_date=format_date(supply.updatedDate),
                                              status_id=supply.statusID,
                                              box_type_id=supply.boxTypeID,
                                              is_box_on_pallet=supply.isBoxOnPallet))

        if len(answer.result) < limit:
            break
        offset += limit

    logger.info(f"Количество строк: {len(list_supplies)}")
    db_conn.add_wb_supplies(list_supplies=list_supplies)


async def main_wb_supplies(retries: int = 6) -> None:
    try:
        db_conn = WBDbConnection()

        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="WB")
        date_now = datetime.now(tz=timezone(timedelta(hours=3))).replace(hour=0, minute=0, second=0, microsecond=0)
        from_date = date_now - timedelta(days=30)
        to_date = date_now + timedelta(days=1) - timedelta(microseconds=1)

        for client in clients:
            if client.name_company != "TiVi":
                continue
            try:
                logger.info(f'Сбор информации о поставках магазина {client.name_company} '
                            f'за период с {from_date.date().isoformat()} по {to_date.date().isoformat()}')
                await get_supplies(db_conn=db_conn,
                                   client_id=client.client_id,
                                   api_key=client.api_key,
                                   from_date=from_date,
                                   to_date=to_date)
            except ClientError as e:
                logger.error(f'{e}')
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_wb_supplies(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_wb_supplies())
    loop.stop()
