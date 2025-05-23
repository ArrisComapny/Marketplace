import asyncio
import logging

import nest_asyncio

from datetime import datetime

from sqlalchemy.exc import OperationalError

from ozon_sdk.errors import ClientError
from ozon_sdk.ozon_api import OzonApi
from database import OzDbConnection
from data_classes import DataOzStock

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def get_stocks(db_conn: OzDbConnection, client_id: str, api_key: str) -> None:
    """
        Получает список расходов по хранению для указанного клиента за определенный период времени.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
    """
    list_stocks = []
    product_ids = {}

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)

    visibility_params = ['ALL', 'ARCHIVED']

    for visibility in visibility_params:
        cursor = None
        total = 1000

        while total >= 1000:
            answer = await api_user.get_product_info_stocks(limit=1000, cursor=cursor, visibility=visibility)

            for item in answer.items:
                for stock in item.stocks:
                    if stock.type in ['fbo']:
                        if stock.reserved or stock.present:
                            vendor_code = item.offer_id
                            size = '0'
                            for s in ['/xs', '/s', '/m', '/м', '/l', '/xl', '/2xl']:
                                if vendor_code.lower().endswith(s):
                                    size = vendor_code.split('/')[-1].upper()
                                    vendor_code = '/'.join(vendor_code.split('/')[:-1])
                                    break
                            product_ids[str(item.product_id)] = None
                            list_stocks.append(DataOzStock(date=datetime.today().date(),
                                                           client_id=client_id,
                                                           sku=str(stock.sku),
                                                           vendor_code=vendor_code,
                                                           size=size,
                                                           quantity=stock.present,
                                                           reserved=stock.reserved))
            total = answer.total
            cursor = answer.cursor

    logger.info(f"Количсетво строк: {len(list_stocks)}")
    db_conn.add_oz_stock_entry(list_stocks=list_stocks)


async def main_oz_stock(retries: int = 6) -> None:
    try:
        db_conn = OzDbConnection()

        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="Ozon")

        for client in clients:
            try:
                logger.info(f'Сбор информации о остатках на складах {client.name_company}')
                await get_stocks(db_conn=db_conn,
                                 client_id=client.client_id,
                                 api_key=client.api_key)
            except ClientError as e:
                logger.error(f'{e}')
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_oz_stock(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_oz_stock())
    loop.stop()
