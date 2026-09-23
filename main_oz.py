import asyncio
import logging

import nest_asyncio

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import OperationalError

from database import OzDbConnection
from ozon_sdk.ozon_api import OzonApi
from ozon_sdk.entities import FinanceAccrual, FinanceAccrualMoney
from data_classes import DataOperation
from ozon_sdk.errors import ClientError

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

# Лимит accrual/postings — до 200 отправлений за запрос
POSTINGS_CHUNK = 200
# Тип начисления «Вознаграждение за продажу» в справочнике /v1/finance/accrual/types
SALE_COMMISSION_TYPE_ID = 69


def _f(money: FinanceAccrualMoney | None) -> float:
    return round(float(money.amount), 2) if money and money.amount is not None else 0.0


async def get_accruals(api_user: OzonApi, date: str) -> list[FinanceAccrual]:
    """Все начисления кабинета за день (пагинация по last_id)."""
    accruals, last_id = [], ''
    while True:
        answer = await api_user.get_finance_accrual_by_day(date=date, last_id=last_id)
        accruals.extend(answer.accruals)
        if not answer.accruals or not answer.last_id:
            break
        last_id = answer.last_id
    return accruals


async def get_quantities(api_user: OzonApi, posting_numbers: list[str]) -> dict:
    """{(posting_number, sku): quantity} из accrual/postings (в by-day количества нет)."""
    quantities = {}
    posting_numbers = sorted(set(posting_numbers))
    for start in range(0, len(posting_numbers), POSTINGS_CHUNK):
        answer = await api_user.get_finance_accrual_postings(posting_numbers=posting_numbers[start:start + POSTINGS_CHUNK])
        for posting in answer.posting_accruals:
            for line in posting.accruals:
                key = (posting.posting_number, str(line.sku))
                # приоритет строке «Вознаграждение за продажу», иначе любая строка с количеством
                if line.type_id == SALE_COMMISSION_TYPE_ID or key not in quantities:
                    if line.quantity:
                        quantities[key] = line.quantity
    return quantities


async def add_oz_main_entry(db_conn: OzDbConnection, client_id: str, api_key: str, date_now: datetime) -> None:
    """
        Добавление записей в таблицу `oz_main_table` за указанную дату.
        Источник — начисления finance/accrual/by-day (замена отключённого finance/transaction/list):
        строка создаётся по каждому начислению продажи/возврата товара, суммы берутся из него же.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            date_now (datetime): Дата начислений.
    """

    accrual_date = date_now.date()
    logger.info(f"За период с <{date_now}> до <{date_now + timedelta(days=1) - timedelta(microseconds=1)}>")

    list_operation = []
    dict_sku = db_conn.get_oz_sku_vendor_code(client_id=client_id)

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)

    accruals = await get_accruals(api_user, date=accrual_date.isoformat())

    # Продажи и возвраты — начисления категории POSTING с блоком commission у товара
    sales = []
    for accrual in accruals:
        if accrual.accrued_category != 'POSTING' or not accrual.posting:
            continue
        for product in accrual.posting.products:
            if product.commission:
                sales.append((accrual, product))

    quantities = await get_quantities(api_user, [accrual.unit_number for accrual, _ in sales])

    for accrual, product in sales:
        posting_number = accrual.unit_number
        delivery_schema = (accrual.posting.delivery_schema or '').upper()   # Fbo -> FBO
        sku = str(product.sku)

        sale = _f(product.commission.sale_amount)
        commission = _f(product.commission.commission)
        bonus = round(_f(product.commission.bonus) + _f(product.commission.coinvestment), 2)

        # Отмена/возврат приходит отдельным начислением с отрицательной суммой продажи
        type_of_transaction = 'delivered' if sale >= 0 else 'cancelled'
        quantity = quantities.get((posting_number, sku), 1)

        # sale и bonus — за единицу товара, commission — общая (так исторически заполнена таблица)
        if quantity > 1:
            sale = round(sale / quantity, 2)
            bonus = round(bonus / quantity, 2)
        if type_of_transaction == 'cancelled':
            quantity = -quantity

        # Артикул продавца: справочник карточек; для уценённых SKU — основной SKU
        if sku not in dict_sku:
            answer_info = await api_user.get_product_info_discounted(discounted_skus=[sku])
            for info in answer_info.items:
                if sku == str(info.discounted_sku):
                    sku = str(info.sku)
        vendor_code = dict_sku.get(sku)
        if not vendor_code:
            if delivery_schema == 'FBO':
                answer_fb = await api_user.get_posting_fbo(posting_number=posting_number, analytics_data=True,
                                                           financial_data=True, translit=True)
            elif delivery_schema in ['FBS', 'RFBS']:
                answer_fb = await api_user.get_posting_fbs(posting_number=posting_number, analytics_data=True,
                                                           financial_data=True, translit=True)
            else:
                answer_fb = None
            if answer_fb:
                for fb_product in answer_fb.result.products:
                    if str(fb_product.sku) == str(product.sku):
                        vendor_code = fb_product.offer_id
            if not vendor_code:
                logger.warning(f'Не найден артикул для sku {sku} ({posting_number})')
                continue

        # Добавление операции в список
        list_operation.append(DataOperation(client_id=client_id,
                                            accrual_date=accrual_date,
                                            type_of_transaction=type_of_transaction,
                                            vendor_code=vendor_code,
                                            delivery_schema=delivery_schema,
                                            posting_number=posting_number,
                                            sku=sku,
                                            sale=sale,
                                            quantities=quantity,
                                            commission=commission,
                                            bonus=bonus))

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
                                        date_now=date_now - timedelta(days=1))
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
