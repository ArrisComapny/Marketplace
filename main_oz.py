import asyncio
import logging

import nest_asyncio

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import OperationalError

from database import OzDbConnection
from ozon_sdk.ozon_api import OzonApi
from data_classes import DataOperation
from ozon_sdk.errors import ClientError

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def add_oz_main_entry(db_conn: OzDbConnection, client_id: str, api_key: str, date_now: datetime) -> None:
    """
        Добавление записей в таблицу `oz_main_table` за указанную дату.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            date_now (datetime): Начальная дата периода.
    """

    from_date = date_now - timedelta(days=1)
    to_date = date_now - timedelta(microseconds=1)
    logger.info(f"За период с <{from_date}> до <{to_date}>")

    page = 1
    list_operation = []
    list_sku = list(db_conn.get_oz_sku_vendor_code(client_id=client_id).keys())
    operation_type = {"OperationAgentDeliveredToCustomer": "delivered",
                      "ClientReturnAgentOperation": "cancelled"}

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)

    while True:
        # Получение списка финансовых транзакций
        answer = await api_user.get_finance_transaction_list(from_field=from_date.isoformat(),
                                                             to=to_date.isoformat(),
                                                             operation_type=[*operation_type.keys()],
                                                             page=page)

        # Обработка полученных результатов
        for operation in answer.result.operations:

            # Извлечение информации о доставке и отправлении
            type_of_transaction = operation_type.get(operation.operation_type)  # Тип операции
            if not type_of_transaction:
                continue

            delivery_schema = operation.posting.delivery_schema  # Склад
            posting_number = operation.posting.posting_number  # Номер отправления
            accrual_date = operation.operation_date.date()  # Дата принятия учёта
            sku_transaction = [str(item.sku) for item in operation.items]

            # Получение дополнительной информации о товаре в зависимости от схемы доставки
            if delivery_schema == 'FBO':
                answer_fb = await api_user.get_posting_fbo(posting_number=posting_number,
                                                           analytics_data=True,
                                                           financial_data=True,
                                                           translit=True)
            elif delivery_schema in ['FBS', 'RFBS']:
                answer_fb = await api_user.get_posting_fbs(posting_number=posting_number,
                                                           analytics_data=True,
                                                           financial_data=True,
                                                           translit=True)
            else:
                continue

            # Обработка информации о товаре
            for product in answer_fb.result.products:
                sku = str(product.sku)  # Артикул продукта внутри системы Ozon

                if sku not in sku_transaction:
                    continue

                sku_transaction.remove(sku)

                vendor_code = product.offer_id  # Артикул продукта
                sale = round(float(product.price), 2)  # Стоимость продажи товара
                quantities = product.quantity  # Количество

                for financial_data_product in answer_fb.result.financial_data.products:
                    if financial_data_product.product_id == product.sku:
                        commission = round(financial_data_product.commission_amount, 2)
                        bonus = round(financial_data_product.price - financial_data_product.customer_price, 2)
                        break
                else:
                    commission = None
                    bonus = None

                if type_of_transaction == "cancelled":
                    sale = -sale
                    quantities = -len([item for item in operation.items if item.sku == product.sku])
                    if commission:
                        commission = round((commission / product.quantity) * quantities, 2)
                    if bonus:
                        bonus = round((bonus / product.quantity) * quantities, 2)

                if sku not in list_sku:
                    answer_info = await api_user.get_product_info_discounted(discounted_skus=[sku])
                    for info in answer_info.items:
                        if sku == str(info.discounted_sku):
                            sku = str(info.sku)

                # Добавление операции в список
                list_operation.append(DataOperation(client_id=client_id,
                                                    accrual_date=accrual_date,
                                                    type_of_transaction=type_of_transaction,
                                                    vendor_code=vendor_code,
                                                    delivery_schema=delivery_schema,
                                                    posting_number=posting_number,
                                                    sku=sku,
                                                    sale=sale,
                                                    quantities=quantities,
                                                    commission=commission,
                                                    bonus=bonus))

        # Получение дополнительных страниц результатов
        if page >= answer.result.page_count:
            break

        page += 1

    logger.info(f"Количество записей операций: {len(list_operation)}")
    db_conn.add_oz_operation(list_operations=list_operation)


async def main_func_oz(retries: int = 6) -> None:
    try:
        db_conn = OzDbConnection()
        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="Ozon")

        date_now = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        for client in clients:
            try:
                logger.info(f"Добавление в базу данных компании '{client.name_company}'")
                await add_oz_main_entry(db_conn=db_conn,
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
