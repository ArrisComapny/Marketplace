import asyncio
from typing import Type

import nest_asyncio
import logging

from datetime import datetime, timedelta, date

from sqlalchemy.exc import OperationalError

from ozon_sdk.errors import ClientError
from database import OzDbConnection, Client
from ozon_sdk.ozon_api import OzonApi, OzonPerformanceAPI
from data_classes import DataOzProductCard, DataOzStatisticCardProduct, DataOzAdvert, DataOzStatisticAdvert, \
    DataOzAdvertDailyBudget

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def add_adverts(db_conn: OzDbConnection, client_id: str, performance_id: str, client_secret: str,
                      from_date: date, name: str = '') -> None:
    """
        Обновление записей данных РК и бюджета РК за указанную дату.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            performance_id (str): ID рекламного кабинета.
            client_secret (str): SECRET KEY рекламного кабинета.
            from_date (date): Дата, за которую обновилсь данные бюджета РК.
    """
    time_format = "%Y-%m-%d"

    adverts_list = []
    adverts_daily_budget = []

    # Инициализация API-клиента Ozon
    api_user = OzonPerformanceAPI(client_id=performance_id, client_secret=client_secret)

    # Получение списка РК
    answer = await api_user.get_client_campaign()

    # Обработка полученных результатов
    for advert in answer.list_field:
        daily_budget = float(advert.dailyBudget)  # Бюджет РК
        if daily_budget and advert.advObjectType == 'SKU':
            adverts_daily_budget.append(DataOzAdvertDailyBudget(advert_id=advert.id_field,
                                                                daily_budget=round(daily_budget / 1000000, 2)))

        create_time = advert.createdAt.date()  # Дата создания РК
        change_time = advert.updatedAt.date()  # Дата последнего изменения РК
        start_time = None
        end_time = None
        if advert.fromDate:
            start_time = datetime.strptime(advert.fromDate, time_format).date()  # Дата последнего старта РК
        if advert.toDate:
            end_time = datetime.strptime(advert.toDate, time_format).date()  # Дата окончания РК

        adverts_list.append(DataOzAdvert(id_advert=advert.id_field,
                                         field_type=advert.advObjectType,
                                         field_status=advert.state,
                                         name_advert=advert.title,
                                         create_time=create_time,
                                         change_time=change_time,
                                         start_time=start_time,
                                         end_time=end_time))

    logger.info(f"{name} Обновление информации о рекламных компаний")
    db_conn.add_oz_adverts(client_id=client_id, adverts_list=adverts_list, name=name)
    logger.info(f"{name} Добавление данных по бюджетам РК")
    company_ids = db_conn.get_oz_adverts_id(client_id=client_id)
    daily_budget = [row for row in adverts_daily_budget if row.advert_id in company_ids]
    db_conn.add_oz_adverts_daily_budget(date=from_date, adverts_daily_budget=daily_budget, name=name)


async def get_products_ids(client_id: str, api_key: str) -> list[str]:
    """
        Получения списка ID товаров.

        Args:
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.

        Returns:
            List[str]: Список ID товаров.
    """
    list_product_ids = []

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)

    visibility_params = ['ALL', 'ARCHIVED']

    for visibility in visibility_params:
        last_id = None
        total = 1000

        # Получение всех страниц товаров
        while total >= 1000:
            # Получение списка товаров
            answer = await api_user.get_product_list(limit=1000, last_id=last_id, visibility=visibility)

            # Обработка полученных результатов
            for item in answer.result.items:
                list_product_ids.append(str(item.product_id))
            total = answer.result.total
            last_id = answer.result.last_id

    return list_product_ids


async def add_card_products(db_conn: OzDbConnection, client_id: str, api_key: str, name: str = '') -> None:
    """
        Обновление записей в таблице `oz_card_product` за указанную дату.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
    """
    list_card_product = []

    # Получение id товаров по ID кабинета
    list_product_ids = await get_products_ids(client_id=client_id, api_key=api_key)

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)

    # Запрос карточек товара по 100 товаров за цикл
    for ids in [list_product_ids[i:i + 100] for i in range(0, len(list_product_ids), 100)]:
        # Получение списка карточек товаров
        answer = await api_user.get_product_info_list(product_id=ids)
        # Получение списка атрибутов товаров
        attributes = await api_user.get_products_info_attributes(product_id=[str(product) for product in ids],
                                                                 limit=1000)

        # Обработка полученных результатов
        for item in answer.items:
            vendor_code = item.offer_id  # Артикул товара в системе продавца
            brand = None
            category = None

            for product in attributes.result:
                if product.id_field == item.id_field:
                    for attribute in product.attributes:
                        if attribute.attribute_id == 8229:
                            category = attribute.values[0].value  # Категория товаров
                        elif attribute.attribute_id == 85:
                            brand = attribute.values[0].value  # Брэнд товара

            discount_price = round(float(item.price), 2)

            if item.old_price:
                price = round(float(item.old_price), 2)
            else:
                price = discount_price

            for source in item.sources:
                # Сбор информации для каждого артикула Ozon товара
                link = f"https://www.ozon.ru/product/{source.sku}"  # Ссылка на товар
                created_at = source.created_at.date()
                list_card_product.append(DataOzProductCard(sku=str(source.sku),
                                                           client_id=client_id,
                                                           vendor_code=vendor_code,
                                                           brand=brand,
                                                           category=category,
                                                           link=link,
                                                           price=price,
                                                           discount_price=discount_price,
                                                           created_at=created_at))

    logger.info(f"{name} Обновление информации о карточках товаров")
    db_conn.add_oz_cards_products(list_card_product=list_card_product, name=name)


async def add_statistics_card_products(db_conn: OzDbConnection, client_id: str, api_key: str,
                                       date_yesterday: date, name: str = '') -> None:
    """
        Получение списка статистики карточек товара за указанную дату.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            date_yesterday (datetime): Дата, за которую собираются данные.
    """
    offset = 0
    limit = 1000

    list_statistics_card_products = []

    #  Метрики для КТ
    metrics = [
        'ordered_units',
        'revenue',
        'hits_tocart_search',
        'hits_tocart_pdp',
        'session_view_search',
        'session_view_pdp',
        'returns',
        'cancellations',
        'delivered_units'
    ]

    # Инициализация API-клиента Ozon
    api_user = OzonApi(client_id=client_id, api_key=api_key)

    while True:
        # Получение списка статистик по КТ
        answer = await api_user.get_analytics_data(date_from=(date_yesterday - timedelta(days=30)).isoformat(),
                                                   date_to=date_yesterday.isoformat(),
                                                   dimension=['sku', 'day'],
                                                   limit=limit,
                                                   metrics=metrics,
                                                   offset=offset)

        # Получение sku товаров по ID кабинета продавца
        list_sku = db_conn.get_oz_sku_vendor_code(client_id=client_id)

        # Обработка полученных результатов
        for product in answer.result.data:
            sku = product.dimensions[0].id_field  # Артикул товара
            field_date = datetime.strptime(product.dimensions[1].id_field, '%Y-%m-%d').date()

            # Фильтруем только те товары, что есть в БД
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
                        break
            if sku not in list_sku:
                continue
            metrics_round = [round(metric, 2) for metric in product.metrics]  # Список значений метрик

            # Проверка на Премиум
            if len(metrics_round) < len(metrics):
                # logger.error(f"{client_id} Статистика не доступна из-за отсутсвия Премиума")
                metrics_round = metrics_round[:2]
                metrics_round.extend([0, 0, 0, 0, 0, 0, 0])
                # limit = 0
                # break

            # Проверка на полностью нулевую статистику
            if not sum(metrics_round):
                continue

            data = dict(zip(metrics, metrics_round))
            list_statistics_card_products.append(
                DataOzStatisticCardProduct(sku=sku,
                                           date=field_date,
                                           add_to_cart_from_search_count=int(data.get('hits_tocart_search')),
                                           add_to_cart_from_card_count=int(data.get('hits_tocart_pdp')),
                                           view_search=int(data.get('session_view_search')),
                                           view_card=int(data.get('session_view_pdp')),
                                           orders_count=int(data.get('ordered_units')),
                                           orders_sum=round(float(data.get('revenue')), 2),
                                           delivered_count=int(data.get('delivered_units')),
                                           returns_count=int(data.get('returns')),
                                           cancel_count=int(data.get('cancellations'))
                                           ))

        # Получение остальных страниц результата
        if not limit or len(answer.result.data) < limit:
            break

        offset += limit

    # Агрегирование данных
    aggregate = {}
    for row in list_statistics_card_products:
        key = (row.sku, row.date)
        if key in aggregate:
            aggregate[key].append((row.add_to_cart_from_search_count,
                                   row.add_to_cart_from_card_count,
                                   row.view_search,
                                   row.view_card,
                                   row.orders_count,
                                   row.orders_sum,
                                   row.delivered_count,
                                   row.returns_count,
                                   row.cancel_count))
        else:
            aggregate[key] = [(row.add_to_cart_from_search_count,
                               row.add_to_cart_from_card_count,
                               row.view_search,
                               row.view_card,
                               row.orders_count,
                               row.orders_sum,
                               row.delivered_count,
                               row.returns_count,
                               row.cancel_count)]
    list_statistics_card_products = []
    for key, value in aggregate.items():
        sku, field_date = key
        add_to_cart_from_search_count = sum([val[0] for val in value])
        add_to_cart_from_card_count = sum([val[1] for val in value])
        view_search = round(sum([val[2] for val in value]), 2)
        view_card = sum([val[3] for val in value])
        orders_count = sum([val[4] for val in value])
        orders_sum = sum([val[5] for val in value])
        delivered_count = sum([val[6] for val in value])
        returns_count = sum([val[7] for val in value])
        cancel_count = sum([val[8] for val in value])

        list_statistics_card_products.append(DataOzStatisticCardProduct(
            sku=sku,
            date=field_date,
            add_to_cart_from_search_count=add_to_cart_from_search_count,
            add_to_cart_from_card_count=add_to_cart_from_card_count,
            view_search=view_search,
            view_card=view_card,
            orders_count=orders_count,
            orders_sum=round(orders_sum, 2),
            delivered_count=delivered_count,
            returns_count=returns_count,
            cancel_count=cancel_count
        ))

    logger.info(f"{name} Количество записей: {len(list_statistics_card_products)}")
    db_conn.add_oz_statistics_card_products(list_card_product=list_statistics_card_products, name=name)


async def add_statistic_adverts(db_conn: OzDbConnection, client_id: str, performance_id: str, client_secret: str,
                                from_date: date, name: str = '') -> None:
    """
        Добавление статистики карточек товара за указанную дату.

        Args:
            db_conn (OzDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            performance_id (str): ID рекламного кабинета.
            client_secret (str): SECRET KEY рекламного кабинета кабинета.
            from_date (date): Дата, за которую собираются данные.
    """
    list_statistics_advert = []
    adverts_ids = []

    # Инициализация API-клиента Ozon
    api_user = OzonPerformanceAPI(client_id=performance_id, client_secret=client_secret)

    # Получения статистики РК за дату
    answer = await api_user.get_client_statistics_daily_json(date_from=from_date.isoformat(),
                                                             date_to=from_date.isoformat())

    stat_adverts = {row.id_field: row for row in answer.rows}

    company_ids = db_conn.get_oz_adverts_id(client_id=client_id)  # РК и типы РК магазина
    list_sku = db_conn.get_oz_sku_vendor_code(client_id=client_id)  # sku товаров магазина

    # Обработка полученных результатов
    for advert_id, stat in stat_adverts.items():
        if company_ids[advert_id] == 'SEARCH_PROMO':
            adverts_ids.append(advert_id)
        else:
            # Получение объектов РК
            try:
                answer_sku = await api_user.get_client_campaign_objects(campaign_id=advert_id)
            except ClientError:
                adverts_ids.append(advert_id)
                continue

            if not answer_sku:
                continue

            skus = answer_sku.list_field
            if len(skus) > 1:
                adverts_ids.append(advert_id)
            elif len(skus) == 1:
                sku = skus[0].id_field
                if sku not in list_sku:
                    continue

                if '-' in stat.date:
                    field_date = datetime.strptime(stat.date, '%Y-%m-%d').date()
                else:
                    field_date = datetime.strptime(stat.date, '%d.%m.%Y').date()
                sum_cost = round(float(stat.moneySpent.replace(',', '.')), 2)  # Рассход РК

                # Сумма зазаков
                if stat.ordersMoney is None:
                    sum_price = 0
                else:
                    sum_price = round(float(stat.ordersMoney.replace(',', '.')), 2)
                list_statistics_advert.append(DataOzStatisticAdvert(client_id=client_id,
                                                                    date=field_date,
                                                                    advert_id=advert_id,
                                                                    sku=sku,
                                                                    views=int(stat.views or 0),
                                                                    clicks=int(stat.clicks or 0),
                                                                    sum_cost=sum_cost,
                                                                    orders_count=int(stat.orders or 0),
                                                                    sum_price=sum_price))

    # Запрос статистики РК по 10 компаний за цикл
    for ids in [adverts_ids[i:i + 10] for i in range(0, len(adverts_ids), 10)]:
        try:
            answer_stat = await api_user.get_client_statistics_json(campaigns=ids,
                                                                    date_from=from_date.isoformat(),
                                                                    date_to=from_date.isoformat(),
                                                                    group_by='DATE')
        except ClientError:
            continue
        uuid = answer_stat.UUID  # Получение UUID отчёта

        # Проверка готовности отчёта
        link = None
        while link != 'OK':
            await asyncio.sleep(30)
            answer_uuid = await api_user.get_client_statistics_uuid(uuid=uuid)
            link = answer_uuid.state
            if link == 'ERROR':
                logger.info(f"Ошибка создания отчёта по РК: {client_id}={ids}")
                break
        else:
            # Запрос на получение отчёта
            answer_report = await api_user.get_client_statistics_report(uuid=uuid)

            # Обработка полученных результатов
            for advert in answer_report.result:
                advert_id = advert.field_id  # ID РК
                for row in advert.statistic.report.rows:
                    sku = row.sku  # Артикул Ozon товара
                    if sku not in list_sku:
                        continue
                    # Дата статистики
                    if '-' in row.date:
                        field_date = datetime.strptime(row.date, '%Y-%m-%d').date()
                    else:
                        field_date = datetime.strptime(row.date, '%d.%m.%Y').date()
                    sum_cost = round(float(row.moneySpent.replace(',', '.')), 2)  # Рассход РК

                    # Сумма зазаков
                    if row.ordersMoney is None:
                        sum_price = 0
                    else:
                        sum_price = round(float(row.ordersMoney.replace(',', '.')), 2)

                    list_statistics_advert.append(DataOzStatisticAdvert(client_id=client_id,
                                                                        date=field_date,
                                                                        advert_id=advert_id,
                                                                        sku=sku,
                                                                        views=int(row.views or 0),
                                                                        clicks=int(row.clicks or 0),
                                                                        sum_cost=sum_cost,
                                                                        orders_count=int(row.orders or 0),
                                                                        sum_price=sum_price))

    # Агрегирование данных
    aggregate = {}
    for stat in list_statistics_advert:
        key = (
            stat.client_id,
            stat.date,
            stat.advert_id,
            stat.sku
        )
        if key in aggregate:
            aggregate[key].append((stat.views, stat.clicks, stat.sum_cost, stat.orders_count, stat.sum_price))
        else:
            aggregate[key] = [(stat.views, stat.clicks, stat.sum_cost, stat.orders_count, stat.sum_price)]
    list_statistics_advert = []
    for key, value in aggregate.items():
        client_id, field_date, advert_id, sku = key
        views = sum([val[0] for val in value])
        clicks = sum([val[1] for val in value])
        sum_cost = round(sum([val[2] for val in value]), 2)
        orders_count = sum([val[3] for val in value])
        sum_price = sum([val[4] for val in value])

        list_statistics_advert.append(DataOzStatisticAdvert(client_id=client_id,
                                                            date=field_date,
                                                            advert_id=advert_id,
                                                            sku=sku,
                                                            views=views,
                                                            clicks=clicks,
                                                            sum_cost=sum_cost,
                                                            orders_count=orders_count,
                                                            sum_price=sum_price))

    logger.info(f"{name} Количество записей: {len(list_statistics_advert)}")
    db_conn.add_oz_statistics_adverts(list_statistics_advert=list_statistics_advert, name=name)

readiness_check = {}
check_func = {'cards': False, 'adverts': False, 'stat_cards': False, 'stat_adverts': False}


async def statistic(db_conn: OzDbConnection, client: Type[Client], date_yesterday: datetime.date):
    try:
        print(f"{client.name_company}: {readiness_check[client.name_company]}")

        # Получение данных рекламного кабинета магазина
        performance = db_conn.get_oz_performance(client_id=client.client_id)

        if not readiness_check[client.name_company]['cards']:
            await add_card_products(db_conn=db_conn, client_id=client.client_id, api_key=client.api_key,
                                    name=client.name_company)
            readiness_check[client.name_company]['cards'] = True
            logger.info(f"Сбор карточек товаров {client.name_company}")

        if not readiness_check[client.name_company]['adverts']:
            await add_adverts(db_conn=db_conn,
                              client_id=client.client_id,
                              performance_id=performance.performance_id,
                              client_secret=performance.client_secret,
                              from_date=date_yesterday,
                              name=client.name_company)
            readiness_check[client.name_company]['adverts'] = True
            logger.info(f"Сбор рекламных компаний {client.name_company}")

        if not readiness_check[client.name_company]['stat_cards']:
            await add_statistics_card_products(db_conn=db_conn,
                                               client_id=client.client_id,
                                               api_key=client.api_key,
                                               date_yesterday=date_yesterday,
                                               name=client.name_company)
            readiness_check[client.name_company]['stat_cards'] = True
            logger.info(f"Статистика карточек товара за {date_yesterday.isoformat()}")

        if not readiness_check[client.name_company]['stat_adverts']:
            await add_statistic_adverts(db_conn=db_conn,
                                        client_id=client.client_id,
                                        performance_id=performance.performance_id,
                                        client_secret=performance.client_secret,
                                        from_date=date_yesterday,
                                        name=client.name_company)
            readiness_check[client.name_company]['stat_adverts'] = True
            logger.info(f"Статистика рекламы за {date_yesterday.isoformat()}")

        if all(readiness_check[client.name_company].values()):
            readiness_check.pop(client.name_company)
    except ClientError as e:
        logger.error(f'{e}')
        readiness_check.pop(client.name_company)


async def main_oz_advert(retries: int = 6) -> None:
    try:
        db_conn = OzDbConnection()
        db_conn.start_db()
        global readiness_check

        clients = db_conn.get_clients(marketplace="Ozon")

        # for day in range(47, 16, -1):

        if not readiness_check:
            for client in clients:
                readiness_check[client.name_company] = check_func.copy()

        date_yesterday = (datetime.now() - timedelta(days=1)).date()

        # Не более 5 кабинетов параллельно (лимит Ozon Performance:
        # 5 одновременных выгрузок статистики на организацию).
        semaphore = asyncio.Semaphore(5)

        async def statistic_limited(client):
            async with semaphore:
                await statistic(db_conn=db_conn, client=client, date_yesterday=date_yesterday)

        tasks = []

        for client in clients:
            if client.name_company not in readiness_check.keys():
                continue
            tasks.append(statistic_limited(client))

        await asyncio.gather(*tasks)

    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_oz_advert(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_oz_advert())
    loop.stop()
