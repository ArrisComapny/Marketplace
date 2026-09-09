import asyncio
import logging

import nest_asyncio

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import OperationalError

from database import OzDbConnection
from ozon_sdk.ozon_api import OzonApi
from ozon_sdk.entities import FinanceAccrual, FinanceAccrualMoney
from data_classes import DataOzService
from ozon_sdk.errors import ClientError

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

# Окно сбора: позавчера и вчера — Ozon дописывает начисления задним числом, второй проход их подхватывает
DAYS = 2

# Операции по отправлениям в терминах прежнего метода: по товару с блоком commission —
# доставка (продажа > 0) или возврат покупателем (продажа < 0); без commission — обработка возврата/отмены
OP_DELIVERED = ('OperationAgentDeliveredToCustomer', 'Доставка покупателю')
OP_CLIENT_RETURN = ('ClientReturnAgentOperation', 'Получение возврата, отмены, невыкупа от покупателя')
OP_ITEM_RETURN = ('OperationItemReturn', 'Доставка и обработка возврата, отмены, невыкупа')


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


async def add_oz_services(db_conn: OzDbConnection, client_id: str, api_key: str, date_now: datetime,
                          types: dict) -> None:
    """
        Добавление записей в таблицу `oz_services` за указанную дату.
        Источник — начисления finance/accrual/by-day (замена отключённого finance/transaction/list):
        услуги доставки приходят по каждому товару отправления, товарные и прочие начисления — отдельно.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            date_now (datetime): Дата начислений.
            types (dict): Справочник начислений {type_id: (name, description)}.
    """
    accrual_date = date_now.date()
    logger.info(f"За дату <{accrual_date}>")

    list_services = []
    dict_sku = db_conn.get_oz_sku_vendor_code(client_id=client_id)

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)

    async def resolve_sku(sku: str) -> str:
        """Для уценённых SKU — основной SKU."""
        if sku and sku not in dict_sku:
            answer_info = await api_user.get_product_info_discounted(discounted_skus=[sku])
            for info in answer_info.items:
                if sku == str(info.discounted_sku):
                    return str(info.sku)
        return sku

    def type_name(type_id: int) -> tuple[str, str]:
        name, description = types.get(type_id, (f'type_{type_id}', f'type_{type_id}'))
        return name, description

    def add(operation_type: str, operation_type_name: str, sku: str | None, posting_number: str | None,
            service: str | None, cost: float) -> None:
        list_services.append(DataOzService(client_id=client_id,
                                           date=accrual_date,
                                           operation_type=operation_type,
                                           operation_type_name=operation_type_name,
                                           vendor_code=dict_sku.get(sku) if sku else None,
                                           sku=sku,
                                           posting_number=posting_number or None,
                                           service=service or None,
                                           cost=round(cost, 2)))

    accruals = await get_accruals(api_user, date=accrual_date.isoformat())

    # Неизвестный type_id — справочник устарел, обновляем из API до записи в базу
    type_ids = set()
    for accrual in accruals:
        for product in (accrual.posting.products if accrual.posting else []):
            type_ids.update(fee.type_id for fee in (product.delivery.services if product.delivery else []))
        for item in (accrual.item_fees.fees if accrual.item_fees else []):
            type_ids.update(fee.type_id for fee in item.fees)
        if accrual.non_item_fee:
            type_ids.add(accrual.non_item_fee.type_id)
        type_ids.update(fee.type_id for fee in (accrual.container_fees.fees if accrual.container_fees else []))
    if any(type_id is not None and type_id not in types for type_id in type_ids):
        logger.info("В начислениях встретился неизвестный type_id — обновляю справочник")
        await refresh_accrual_types(db_conn=db_conn, api_user=api_user, types=types)

    for accrual in accruals:
        posting_number = accrual.unit_number

        # Услуги по отправлению (логистика, последняя миля, обратная логистика и т.д.)
        if accrual.posting:
            for product in accrual.posting.products:
                if product.commission:
                    op = OP_DELIVERED if _f(product.commission.sale_amount) >= 0 else OP_CLIENT_RETURN
                else:
                    op = OP_ITEM_RETURN
                sku = await resolve_sku(str(product.sku))
                for fee in (product.delivery.services if product.delivery else []):
                    add(op[0], op[1], sku, posting_number, type_name(fee.type_id)[0], _f(fee.accrued))

        # Начисления по товарам (эквайринг, упаковка, размещение у партнёров...)
        if accrual.item_fees:
            for item in accrual.item_fees.fees:
                sku = await resolve_sku(str(item.sku))
                for fee in item.fees:
                    name, description = type_name(fee.type_id)
                    add(name, description, sku, posting_number, name, _f(fee.accrued))

        # Начисления без привязки к товару (хранение, страховка, штрафы, реклама, подписки...)
        if accrual.non_item_fee and accrual.non_item_fee.type_id is not None:
            name, description = type_name(accrual.non_item_fee.type_id)
            add(name, description, None, posting_number, None, _f(accrual.non_item_fee.accrued))

        if accrual.container_fees:
            for fee in accrual.container_fees.fees:
                name, description = type_name(fee.type_id)
                add(name, description, None, posting_number, name, _f(fee.accrued))

    # Агрегирование данных
    aggregate = {}
    for row in list_services:
        key = (
            row.client_id,
            row.date,
            row.operation_type,
            row.operation_type_name,
            row.vendor_code,
            row.sku,
            row.posting_number,
            row.service
        )
        if key in aggregate:
            aggregate[key] += row.cost
        else:
            aggregate[key] = row.cost
    list_services = []
    for key, cost in aggregate.items():
        client_id, date_now, operation_type, operation_type_name, vendor_code, sku, posting_number, service = key
        list_services.append(DataOzService(client_id=client_id,
                                           date=date_now,
                                           operation_type=operation_type,
                                           operation_type_name=operation_type_name,
                                           vendor_code=vendor_code,
                                           sku=sku,
                                           posting_number=posting_number,
                                           service=service,
                                           cost=round(cost, 2)))

    logger.info(f'Количество записей: {len(list_services)}')
    db_conn.add_oz_services_entry(client_id=client_id, list_services=list_services)


async def refresh_accrual_types(db_conn: OzDbConnection, api_user: OzonApi, types: dict) -> None:
    """
        Обновляет справочник начислений из API и сохраняет в кэш (таблица oz_accrual_types).
        У метода /v1/finance/accrual/types жёсткий лимит (частые 429), поэтому вызывается
        только когда кэш пуст или в данных встретился неизвестный type_id; при неудаче
        типы пишутся как type_<id>, прогон не падает.
    """
    try:
        answer = await api_user.get_finance_accrual_types()
        fresh = {t.id: (t.name, t.description) for t in answer.accrual_types}
        if fresh:
            types.update(fresh)
            db_conn.add_oz_accrual_types(types=fresh)
    except Exception as e:
        logger.error(f"Справочник начислений не получен: {e}")


async def main_oz_services(retries: int = 6) -> None:
    try:
        db_conn = OzDbConnection()

        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="Ozon")

        date_now = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Справочник начислений — из кэша в базе; к API только если кэш пуст
        types = db_conn.get_oz_accrual_types()
        if not types and clients:
            await refresh_accrual_types(db_conn=db_conn,
                                        api_user=OzonApi(client_id=clients[0].client_id, api_key=clients[0].api_key),
                                        types=types)
        logger.info(f"Справочник начислений: {len(types)} типов")

        for client in clients:
            try:
                logger.info(f"Добавление в базу данных компании '{client.name_company}'")
                for day in range(DAYS, 0, -1):
                    await add_oz_services(db_conn=db_conn,
                                          client_id=client.client_id,
                                          api_key=client.api_key,
                                          date_now=date_now - timedelta(days=day),
                                          types=types)
            except ClientError as e:
                logger.error(f'{e}')
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_oz_services(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_oz_services())
    loop.stop()
