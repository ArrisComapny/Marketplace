import io
import csv
import uuid
import asyncio
import logging
import zipfile

import nest_asyncio

from datetime import datetime, timedelta
from sqlalchemy.exc import OperationalError

from wb_sdk.errors import ClientError
from wb_sdk.wb_api import WBApi
from database import WBDbConnection
from data_classes import DataWBAdvert, DataWBCardProduct, DataWBStatisticAdvert, DataWBStatisticCardProduct

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)


async def add_adverts(db_conn: WBDbConnection, client_id: str, api_key: str) -> None:
    """
        Обновление записей данных РК.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
    """
    def format_date(date_format: str) -> datetime.date:
        """Функция форматирования даты."""
        time_format = "%Y-%m-%d"
        return datetime.strptime(date_format.split('T')[0], time_format).date()

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)

    adverts_list = []

    status_dict = {
        7: 'Кампания завершена',
        9: 'Идут показы',
        11: 'Кампания на паузе',
    }
    type_dict = {
        8: 'Автоматическая кампания',
        9: 'Аукцион'
    }

    # Запрос данных по статусу и типу РК
    for status in status_dict.keys():
        for type_field in type_dict.keys():
            # Получение списка РК
            answer_advent = await api_user.get_promotion_adverts(status=status, type_field=type_field)

            # Обработка полученных результатов
            if answer_advent:
                for advert in answer_advent.result:
                    create_time = format_date(date_format=advert.createTime)  # Дата создания РК
                    change_time = format_date(date_format=advert.changeTime)  # Дата последнего изменения РК
                    start_time = format_date(date_format=advert.startTime)  # Дата последнего старта РК
                    end_time = format_date(date_format=advert.endTime)  # Дата окончания РК

                    adverts_list.append(DataWBAdvert(id_advert=str(advert.advertId),
                                                     id_type=advert.type,
                                                     id_status=advert.status,
                                                     name_advert=advert.name,
                                                     create_time=create_time,
                                                     change_time=change_time,
                                                     start_time=start_time,
                                                     end_time=end_time))

    logger.info(f"Обновление информации о рекламных компаний")
    db_conn.add_wb_adverts(client_id=client_id, adverts_list=adverts_list)


async def get_product_card(db_conn: WBDbConnection, client_id: str, api_key: str) -> None:
    """
        Обновление информации о КТ.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
    """
    offset = 0
    limit = 1000

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)

    list_card_product = []

    while True:
        # Получение списка КТ
        answer = await api_user.get_list_goods_filter(limit=limit, offset=offset)

        # Обработка полученных результатов
        for product in answer.data.listGoods:
            price = round(product.sizes[0].price, 2)  # Цена товара
            discount_price = round(product.sizes[0].discountedPrice, 2)  # Цена товара со скидкой
            link = f"https://www.wildberries.ru/catalog/{product.nmID}/detail.aspx"  # Ссылка на товар
            list_card_product.append(DataWBCardProduct(sku=str(product.nmID),
                                                       vendor_code=product.vendorCode,
                                                       client_id=client_id,
                                                       link=link,
                                                       price=price,
                                                       discount_price=discount_price))

        # Получение остальных страниц результата
        if len(answer.data.listGoods) < 1000:
            break

        offset += limit

    logger.info(f"Обновление информации о карточках товаров")
    db_conn.add_wb_cards_products(list_card_product=list_card_product)


async def add_statistic_adverts(db_conn: WBDbConnection, client_id: str, api_key: str,
                                from_date: datetime) -> None:
    """
        Добавление записей в таблицу `wb_statistic_advert` за указанную дату

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            from_date (datetime): Дата, для которой добавляются записи.

        Returns:
                List[DataWBStatisticAdvert]: Список статистики рекламных компаний, удовлетворяющих условию фильтрации.
    """
    end_date = from_date.date()
    start_date = end_date - timedelta(days=30)
    sd = start_date

    # Получение ID РК и время создания и окончания
    adverts = db_conn.get_wb_adverts_id(client_id=client_id, from_date=start_date)
    company_ids = [company_id for company_id in adverts]

    date_list = []

    while sd <= end_date:
        date_list.append(sd.isoformat())
        sd += timedelta(days=1)

    product_advertising_campaign = []

    if not company_ids:
        logger.info(f"Количество РК: 0")
        return

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)

    app_type = {
        0: 'Неизвестно',
        1: 'Сайт',
        32: 'Android',
        64: 'IOS'
    }

    # Запрос статистики РК по 100 компаний за цикл
    for dates in [date_list[i:i + 10] for i in range(0, len(date_list), 10)]:
        filter_company_ids = []
        for company_id in company_ids:
            create = adverts.get(company_id)[0].isoformat()
            end = adverts.get(company_id)[1].isoformat()
            if not all(create > d for d in dates):
                if not all(end < d for d in dates):
                    filter_company_ids.append(company_id)
        if not filter_company_ids:
            continue
        for ids in [company_ids[i:i+100] for i in range(0, len(company_ids), 100)]:
            answer = await api_user.get_fullstats(company_ids=ids, dates=dates)

            # Обработка полученных результатов
            if answer:
                for advert in answer.result:
                    for day in advert.days:
                        for app in day.apps:
                            if app.appType == 0 and app.nm:
                                product_advertising_campaign.append(
                                    DataWBStatisticAdvert(client_id=client_id,
                                                          date=day.date_field,
                                                          views=app.views,
                                                          clicks=app.clicks,
                                                          sum_cost=app.sum,
                                                          atbs=app.atbs,
                                                          orders_count=app.orders,
                                                          shks=app.shks,
                                                          sum_price=app.sum_price,
                                                          sku=str(app.nm[0].nmId),
                                                          advert_id=str(advert.advertId),
                                                          app_type=app_type.get(app.appType))
                                )
                            else:
                                for position in app.nm:
                                    if position.views is not None:
                                        product_advertising_campaign.append(
                                            DataWBStatisticAdvert(client_id=client_id,
                                                                  date=day.date_field,
                                                                  views=position.views,
                                                                  clicks=position.clicks,
                                                                  sum_cost=position.sum,
                                                                  atbs=position.atbs,
                                                                  orders_count=position.orders,
                                                                  shks=position.shks,
                                                                  sum_price=position.sum_price,
                                                                  sku=str(position.nmId),
                                                                  advert_id=str(advert.advertId),
                                                                  app_type=app_type.get(app.appType))
                                        )

    logger.info(f"Количество записей: {len(product_advertising_campaign)}")
    db_conn.add_wb_adverts_statistics(client_id=client_id,
                                      product_advertising_campaign=product_advertising_campaign,
                                      start_date=start_date,
                                      end_date=end_date)


async def get_statistic_card_product(db_conn: WBDbConnection, client_id: str, api_key: str,
                                     from_date: datetime) -> None:
    """
        Получение списка статистики карточек товара за указанную дату.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            from_date (datetime): Дата, за которую собираются данные.
    """
    list_card_product = []

    end_date = from_date.date()
    start_date = end_date - timedelta(days=30)

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)

    new_uuid = str(uuid.uuid4())

    # Создание отчёта статистики КТ
    answer_report = await api_user.get_mm_report_downloads(uuid=new_uuid,
                                                           start_date=start_date.isoformat(),
                                                           end_date=end_date.isoformat())

    if not answer_report.error:
        # Получение отчёта статистики КТ
        for _ in range(3):
            await asyncio.sleep(15)
            try:
                answer_download = await api_user.get_nm_report_downloads_file(uuid=new_uuid)
                zip_file = io.BytesIO(answer_download.file)
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    csv_filename = zip_ref.namelist()[0]
                    with zip_ref.open(csv_filename) as csv_file:
                        csv_reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding='utf-8'))
                        data = [row for row in csv_reader]
                        skus = db_conn.get_wb_sku_vendor_code(client_id=client_id)
                        for row in data:
                            sku = row.get('nmID', 0)
                            vendor_code = skus.get(sku)
                            if not vendor_code:
                                continue
                            list_card_product.append(DataWBStatisticCardProduct(
                                sku=sku,
                                vendor_code=skus.get(sku),
                                client_id=client_id,
                                date=datetime.strptime(row.get('dt'), '%Y-%m-%d').date(),
                                open_card_count=int(row.get('openCardCount', 0)),
                                add_to_cart_count=int(row.get('addToCartCount', 0)),
                                orders_count=int(row.get('ordersCount', 0)),
                                buyouts_count=int(row.get('buyoutsCount', 0)),
                                cancel_count=int(row.get('cancelCount', 0)),
                                orders_sum=round(float(row.get('ordersSumRub', 0)), 2)
                            ))
            except Exception as e:
                logger.warning(f"Ошибка: {str(e)}")

    logger.info(f"Количество записей: {len(list_card_product)}")
    db_conn.add_wb_cards_products_statistics(client_id=client_id, list_card_product=list_card_product)


async def main_wb_advert(retries: int = 6) -> None:
    try:
        db_conn = WBDbConnection()
        db_conn.start_db()
        clients = db_conn.get_clients(marketplace="WB")

        date_now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        from_date = date_now - timedelta(days=1)

        for client in clients[-2:]:
            try:
                logger.info(f"Сбор карточек товаров {client.name_company}")
                await get_product_card(db_conn=db_conn, client_id=client.client_id, api_key=client.api_key)
            except ClientError as e:
                logger.error(f'{e}')

            try:
                logger.info(f"Сбор рекламных компаний {client.name_company}")
                await add_adverts(db_conn=db_conn, client_id=client.client_id, api_key=client.api_key)
            except ClientError as e:
                logger.error(f'{e}')

            try:
                logger.info(f"Статистика карточек товара {client.name_company} за {from_date.date().isoformat()}")
                await get_statistic_card_product(db_conn=db_conn,
                                                 client_id=client.client_id,
                                                 api_key=client.api_key,
                                                 from_date=from_date)
            except ClientError as e:
                logger.error(f'{e}')

            try:
                logger.info(f"Статистика рекламы {client.name_company}")
                await add_statistic_adverts(db_conn=db_conn,
                                            client_id=client.client_id,
                                            api_key=client.api_key,
                                            from_date=from_date)
            except ClientError as e:
                logger.error(f'{e}')

    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_wb_advert(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_wb_advert())
    loop.stop()
