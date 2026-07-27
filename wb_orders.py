import asyncio
import logging

import nest_asyncio

from datetime import timedelta, date

from sqlalchemy.exc import OperationalError

from wb_sdk.errors import ClientError
from wb_sdk.wb_api import WBApi
from data_classes import DataWBOrder
from database import WBDbConnection

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def add_wb_orders_entry(db_conn: WBDbConnection, client_id: str, api_key: str, date_now: date) -> None:
    """
        Получает список заказов для указанного клиента за определенный период времени.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            date_now (date): Начальная дата периода.
                Формат: YYYY-MM-DDTHH:mm:ss.sssZ.
                Пример: 2019-11-25T10:43:06.51Z.
    """
    date_from = date_now - timedelta(days=20)
    logger.info(f"За дату {date_now - timedelta(days=1)}")

    list_orders = []
    added_orders = set()

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)

    # WB отдаёт не более ~80000 строк за один запрос.
    # Выгружаем частями: следующий запрос начинается с lastChangeDate последней строки,
    # пока не придёт пустой ответ.
    next_date_from = date_from.isoformat()
    while True:
        # Получение списка заказов
        answer_orders = await api_user.get_supplier_orders(date_from=next_date_from, flag=0)

        if not answer_orders.result:
            break

        # Обработка полученных результатов
        for order in answer_orders.result:
            order_date = order.date.date()  # Дата заказа
            cancel_date = order.cancelDate.date()  # Дата отмены

            if order_date >= date_now:
                continue
            posting_number = order.srid  # Уникальный идентификатор заказа
            if posting_number in added_orders:  # Строки на границе частей могут дублироваться
                continue
            added_orders.add(posting_number)
            vendor_code = order.supplierArticle  # Артикул продукта
            sku = str(order.nmId)  # Артикул продукта внутри системы WB
            price = round(float(order.priceWithDisc), 2)  # Стоимость продажи товара
            warehouse = order.warehouseName
            warehouse_type = order.warehouseType
            country = order.countryName
            oblast = order.oblastOkrugName
            region = order.regionName

            # Добавление заказа в список
            list_orders.append(DataWBOrder(client_id=client_id,
                                           order_date=order_date,
                                           sku=sku,
                                           vendor_code=vendor_code,
                                           category=order.category,
                                           subject=order.subject,
                                           posting_number=posting_number,
                                           price=price,
                                           is_cancel=order.isCancel,
                                           cancel_date=cancel_date,
                                           warehouse=warehouse,
                                           warehouse_type=warehouse_type,
                                           country=country,
                                           oblast=oblast,
                                           region=region))

        # Меньше лимита — выгрузка полная, дозапрос не нужен
        if len(answer_orders.result) < 80000:
            break

        # Продолжаем с даты изменения последней строки
        next_date_from = answer_orders.result[-1].lastChangeDate.isoformat()
        logger.info(f"Получено {len(list_orders)} строк, продолжаю с {next_date_from}")

        # Лимит endpoint'а: 1 запрос в минуту
        await asyncio.sleep(65)

    logger.info(f"Количество записей: {len(list_orders)}")
    db_conn.add_wb_orders(list_orders=list_orders)


async def main_orders_wb(retries: int = 6) -> None:
    try:
        db_conn = WBDbConnection()
        db_conn.start_db()
        clients = db_conn.get_clients(marketplace="WB")

        date_now = date.today()

        for client in clients:
            try:
                logger.info(f"Добавление в базу данных компании {client.name_company}")
                await add_wb_orders_entry(db_conn=db_conn,
                                          client_id=client.client_id,
                                          api_key=client.api_key,
                                          date_now=date_now)
            except ClientError as e:
                logger.error(f'{e}')
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_orders_wb(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_orders_wb())
    loop.stop()
