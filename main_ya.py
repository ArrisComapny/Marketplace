import asyncio
import nest_asyncio
import logging

from datetime import datetime, timedelta, timezone, date
from sqlalchemy.exc import OperationalError

from data_classes import DataOperation, DataYaCampaigns
from ya_sdk.errors import ClientError
from ya_sdk.ya_api import YandexApi
from database import YaDbConnection

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

# Разовый бэкфилл по дате ОФОРМЛЕНИЯ заказа: задайте обе даты (date(ГГГГ, М, Д)) и
# запустите скрипт, после прогона верните None. Внимание: campaigns/orders с fromDate
# может молча терять заказы — после бэкфилла добирайте хвосты скриптом ya_backfill_orphans.py.
BACKFILL_FROM = None
BACKFILL_TO = None


async def get_campaign_ids(api_key: str) -> list[DataYaCampaigns]:
    list_campaigns = []
    api_user = YandexApi(api_key=api_key)
    answer = await api_user.get_campaigns()
    if answer:
        for campaign in answer.campaigns:
            list_campaigns.append(DataYaCampaigns(client_id=str(campaign.business.field_id),
                                                  campaign_id=str(campaign.field_id),
                                                  name=campaign.domain,
                                                  placement_type=campaign.placementType))
    return list_campaigns


async def get_orders(api_key: str, campaign_id: str,
                     updated_at_from: str = None, updated_at_to: str = None,
                     from_date: str = None, to_date: str = None) -> list[int]:
    list_orders = []
    page = 1

    api_user = YandexApi(api_key=api_key)
    while True:
        answer_orders = await api_user.get_campaigns_orders(campaign_id=campaign_id,
                                                            from_date=from_date,
                                                            to_date=to_date,
                                                            updated_at_from=updated_at_from,
                                                            updated_at_to=updated_at_to,
                                                            status=['DELIVERED'],
                                                            page=page)
        if answer_orders:
            for order in answer_orders.orders:
                list_orders.append(order.id_field)

        if answer_orders.pager is None or answer_orders.pager.pagesCount <= page:
            break

        page += 1

    return list_orders


async def get_operations(client_id: str, campaign_id: str, api_key: str,
                         updated_at_from: str = None, updated_at_to: str = None,
                         from_date: str = None, to_date: str = None) \
        -> list[DataOperation]:
    """
        Получает список операций для указанного клиента за определенный период времени.

        Args:
            client_id (str): ID кабинета.
            campaign_id (str): ID магазина.
            api_key (str): API KEY кабинета.
            updated_at_from (str): Начальная дата периода (в формате строки)
                Формат: YYYY-MM-DDTHH:mm:ss.sssZ.
                Пример: 2019-11-25T10:43:06.51Z.
            updated_at_to (str): Конечная дата периода (в формате строки).
                Формат: YYYY-MM-DDTHH:mm:ss.sssZ.
                Пример: 2019-11-25T10:43:06.51Z.

        Returns:
            list[DataOperation]: Список операций.
    """
    list_operation = []
    date_format = '%Y-%m-%d'

    # Инициализация API-клиента Yandex
    api_user = YandexApi(api_key=api_key)

    # Получение списка заказов
    list_orders = await get_orders(campaign_id=campaign_id,
                                   api_key=api_key,
                                   updated_at_from=updated_at_from,
                                   updated_at_to=updated_at_to,
                                   from_date=from_date,
                                   to_date=to_date)
    if not list_orders:
        return list_operation

    page_token = None

    while True:
        answer = await api_user.get_campaigns_stats_orders(campaign_id=campaign_id,
                                                           orders=list_orders,
                                                           limit=200,
                                                           page_token=page_token)
        if not answer.result:
            break

        for order in answer.result.orders:
            posting_number = str(order.id_field)  # Номер отправления
            accrual_date = datetime.strptime(order.statusUpdateDate.split('T')[0], date_format).date()  # Дата доставки
            for item in order.items:
                vendor_code = item.shopSku
                quantities = item.count
                sku = str(item.marketSku)
                sale = round(sum([price.costPerItem for price in item.prices]), 2)
                bonus = round(sum([price.costPerItem for price in item.prices if price.type != 'BUYER']), 2)
                if item.details:
                    quantities_returned = 0
                    for detail in item.details:
                        if detail.itemStatus == 'REJECTED':
                            quantities -= detail.itemCount
                        elif detail.itemStatus == 'RETURNED':
                            quantities_returned -= detail.itemCount
                    if quantities_returned < 0:
                        list_operation.append(DataOperation(client_id=client_id,
                                                            accrual_date=accrual_date,
                                                            type_of_transaction='cancelled',
                                                            vendor_code=vendor_code,
                                                            delivery_schema=campaign_id,
                                                            posting_number=posting_number,
                                                            sku=sku,
                                                            sale=-sale,
                                                            quantities=quantities_returned,
                                                            bonus=-bonus))
                if quantities > 0:
                    list_operation.append(DataOperation(client_id=client_id,
                                                        accrual_date=accrual_date,
                                                        type_of_transaction='delivered',
                                                        vendor_code=vendor_code,
                                                        delivery_schema=campaign_id,
                                                        posting_number=posting_number,
                                                        sku=sku,
                                                        sale=sale,
                                                        quantities=quantities,
                                                        bonus=bonus))
        if not answer.result.paging.nextPageToken:
            break

        page_token = answer.result.paging.nextPageToken

    return list_operation


async def add_yandex_main_entry(db_conn: YaDbConnection, client_id: str, campaign_id: str, api_key: str,
                                date_now: datetime) -> None:
    """
        Добавление записей в таблицу `ya_main_table` за указанную дату

        Args:
            db_conn (YaDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            campaign_id (str): ID магазина.
            api_key (str): API KEY кабинета.
            date_now (datetime): Дата, для которой добавляются записи.
    """
    if BACKFILL_FROM and BACKFILL_TO:
        operations = []
        chunk_start = BACKFILL_FROM
        while chunk_start <= BACKFILL_TO:
            chunk_end = min(chunk_start + timedelta(days=29), BACKFILL_TO)
            logger.info(f"Бэкфилл по дате оформления с <{chunk_start}> до <{chunk_end}>")
            operations += await get_operations(client_id=client_id,
                                               campaign_id=campaign_id,
                                               api_key=api_key,
                                               from_date=chunk_start.strftime('%d-%m-%Y'),
                                               to_date=chunk_end.strftime('%d-%m-%Y'))
            chunk_start = chunk_end + timedelta(days=1)
    else:
        # 30 дней вместо 10: разовые сбои загрузчика перестают превращаться
        # в невосполнимые потери — у updatedAt-фильтра глубина ~30 дней
        start = date_now - timedelta(days=30)
        end = date_now - timedelta(microseconds=1)

        logger.info(f"За период с <{start}> до <{end}>")
        operations = await get_operations(client_id=client_id,
                                          campaign_id=campaign_id,
                                          api_key=api_key,
                                          updated_at_from=start.isoformat(),
                                          updated_at_to=end.isoformat())

    logger.info(f"Количество записей: {len(operations)}")
    db_conn.add_ya_operation(list_operations=operations)


async def main_func_yandex(retries: int = 6) -> None:
    """
        Основная функция для обновления записей в базе данных.

        Получает список клиентов из базы данных,
        затем для каждого клиента добавляет записи за вчерашний день в таблицу `ya_main_table`.
    """
    try:
        db_conn = YaDbConnection()
        db_conn.start_db()
        clients = db_conn.get_clients(marketplace='Yandex')
        api_key_set = {client.api_key for client in clients}
        for api_key in api_key_set:
            list_campaigns = await get_campaign_ids(api_key=api_key)
            db_conn.add_ya_campaigns(list_campaigns=list_campaigns)

            date_now = datetime.now(tz=timezone(timedelta(hours=3))).replace(hour=0, minute=0, second=0, microsecond=0)

            for campaign in sorted(list_campaigns, key=lambda x: x.client_id):
                client = db_conn.get_client(client_id=campaign.client_id)
                logger.info(f"Добавление в базу данных компании '{client.name_company}' магазина '{campaign.name}'")
                try:
                    await add_yandex_main_entry(db_conn=db_conn,
                                                client_id=client.client_id,
                                                campaign_id=campaign.campaign_id,
                                                api_key=client.api_key,
                                                date_now=date_now)
                except ClientError as e:
                    logger.error(f'{e}')

    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_func_yandex(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_func_yandex())
    loop.stop()
