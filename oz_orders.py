import asyncio
import logging

import nest_asyncio

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import OperationalError

from database import OzDbConnection
from ozon_sdk.ozon_api import OzonApi
from data_classes import DataOzOrder
from ozon_sdk.errors import ClientError

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def add_oz_orders_entry(db_conn: OzDbConnection, client_id: str, api_key: str, date_now: datetime) -> None:
    """
        Добавление записей в таблицу `oz_orders` за указанную дату.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            date_now (datetime): Начальная дата периода.
    """

    from_date = date_now - timedelta(days=30)
    to_date = date_now - timedelta(microseconds=1)
    logger.info(f"За период с <{from_date}> до <{to_date}>")

    limit = 100
    cursor = ""
    list_orders = []
    list_sku = list(db_conn.get_oz_sku_vendor_code(client_id=client_id).keys())

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)
    while True:
        # Получение списка финансовых транзакций
        answer = await api_user.get_posting_fbo_list(since=from_date.isoformat(),
                                                     to=to_date.isoformat(),
                                                     limit=limit,
                                                     cursor=cursor)

        # Обработка полученных результатов
        for order in answer.postings:
            order_date = (order.in_process_at + timedelta(hours=3)).date()
            for product in order.products:
                sku = str(product.sku)
                if sku not in list_sku:
                    answer_info = await api_user.get_product_info_discounted(discounted_skus=[sku])
                    for info in answer_info.items:
                        if sku == str(info.discounted_sku):
                            sku = str(info.sku)

                if sku not in list_sku:
                    answer_info = await api_user.get_product_related_sku_get(skus=[sku])
                    for info in answer_info.items:
                        if str(info.sku) in list_sku:
                            sku = str(info.sku)

                list_orders.append(DataOzOrder(client_id=client_id,
                                               order_date=order_date,
                                               sku=sku,
                                               vendor_code=product.offer_id,
                                               posting_number=order.posting_number,
                                               delivery_schema='FBO',
                                               quantities=product.quantity,
                                               price=round(float(product.price.amount), 2),
                                               status=order.status))

        if answer.has_next:
            cursor = answer.cursor
            continue

        break

    cursor = ""

    while True:
        # Получение списка финансовых транзакций
        answer = await api_user.get_posting_fbs_list(since=from_date.isoformat(),
                                                     to=to_date.isoformat(),
                                                     limit=limit,
                                                     cursor=cursor)

        # Обработка полученных результатов
        for order in answer.postings:
            order_date = (order.in_process_at + timedelta(hours=3)).date()
            for product in order.products:
                sku = str(product.sku)
                if sku not in list_sku:
                    answer_info = await api_user.get_product_info_discounted(discounted_skus=[sku])
                    for info in answer_info.items:
                        if sku == str(info.discounted_sku):
                            sku = str(info.sku)

                if sku not in list_sku:
                    answer_info = await api_user.get_product_related_sku_get(skus=[sku])
                    for info in answer_info.items:
                        if str(info.sku) in list_sku:
                            sku = str(info.sku)

                list_orders.append(DataOzOrder(client_id=client_id,
                                               order_date=order_date,
                                               sku=sku,
                                               vendor_code=product.offer_id,
                                               posting_number=order.posting_number,
                                               delivery_schema='FBS',
                                               quantities=product.quantity,
                                               price=round(float(product.price.amount), 2),
                                               status=order.status))

        if answer.has_next:
            cursor = answer.cursor
            continue

        break

    logger.info(f"Количество записей операций: {len(list_orders)}")
    db_conn.add_oz_orders(list_orders=list_orders)


async def main_func_oz(retries: int = 6) -> None:
    try:
        db_conn = OzDbConnection()
        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="Ozon")

        date_now = datetime.now(tz=timezone(timedelta(hours=3))).replace(hour=0, minute=0, second=0, microsecond=0)

        for client in clients:
            try:
                logger.info(f"Добавление в базу данных компании '{client.name_company}'")
                await add_oz_orders_entry(db_conn=db_conn,
                                          client_id=client.client_id,
                                          api_key=client.api_key,
                                          date_now=date_now)
            except ClientError as e:
                logger.error(f'{e}')
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_func_oz(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_func_oz())
    loop.stop()
