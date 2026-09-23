import os
import gspread
import numpy as np
import pandas as pd

from datetime import datetime, date
from sqlalchemy import create_engine
from oauth2client.service_account import ServiceAccountCredentials

from config import DB_URL

engine = create_engine(DB_URL)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT = 'YandexAdv'

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
PATH_JSON = os.path.join(PROJECT_ROOT, 'templates', 'service-account-432709-1178152e9e49.json')

creds = ServiceAccountCredentials.from_json_keyfile_name(PATH_JSON, SCOPE)
client = gspread.authorize(creds)

spreadsheet = client.open(PROJECT)


def get_worksheet(sheet_name: str, cols: int) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=5, cols=cols)
    return worksheet


def convert_date(x):
    if isinstance(x, str):
        x = datetime.strptime(x, '%Y-%m-%d').date()

    if isinstance(x, date):
        epoch = date(1899, 12, 30)
        delta = x - epoch
        return int(delta.days + (delta.seconds / 86400))

    return x


def write_data(worksheet: gspread.Worksheet, dataframe: pd.DataFrame):
    worksheet.clear()

    df = dataframe.copy()

    for col in df.columns:
        if 'Дата' in col or 'Дата' in col:
            df[col] = df[col].apply(convert_date)

    df = df.replace([np.nan, np.inf, -np.inf], "")

    rows = [df.columns.tolist()] + df.values.tolist()

    worksheet.update(values=rows, range_name='A1')


df_ya_orders = pd.read_sql("""
SELECT
    yo.order_date as "Дата заказа",
    yo.vendor_code as "Артикул",
    (yo.quantities - yo.rejected - yo.returned) as "Количество, шт.",
    yo.price as "Цена, ₽",
    yo.price * (yo.quantities - yo.rejected - yo.returned)  as "Цена общая, ₽",
    COALESCE(yo.bonus, 0) as "Бонус, ₽",
    COALESCE(yo.bonus, 0) * (yo.quantities - yo.rejected - yo.returned)  as "Бонус общий, ₽",
    yo.price - COALESCE(yo.bonus, 0) as "Цена для клиента, ₽",
    (yo.price - COALESCE(yo.bonus, 0)) * (yo.quantities - yo.rejected - yo.returned)  as "Цена общая для клиента, ₽",
    c.entrepreneur as "ИП",
    ymt.accrual_date as "Дата забора"
FROM ya_orders yo
LEFT JOIN clients c ON c.client_id = yo.client_id
LEFT JOIN (SELECT * FROM ya_main_table WHERE type_of_transaction = 'delivered') ymt 
ON ymt.posting_number = yo.posting_number 
WHERE yo.order_date >= '2025-04-01'
AND status NOT IN ('CANCELLED_IN_DELIVERY', 'CANCELLED_IN_PROCESSING', 'CANCELLED_BEFORE_PROCESSING', 'RETURNED')
ORDER BY yo.order_date DESC, c.entrepreneur, yo.vendor_code
""", con=engine)

write_data(worksheet=get_worksheet(sheet_name='Data_orders', cols=len(df_ya_orders.columns) + 5),
           dataframe=df_ya_orders)

df_ya_report_shows_view = pd.read_sql("""
SELECT
    yrs.date as "Дата",
    yrs.vendor_code as "Ваш SKU",
    yrs.name_product as "Название товара",
    yrs.shows as "Показы с бустом продаж, шт.",
    yrs.clicks as "Клики с бустом продаж, шт.",
    yrs.add_to_card as "В корзину с бустом продаж, шт.",
    yrs.orders_count as "Заказанные с бустом продаж, шт.",
    yrs.cpm as "CPM, ₽",
    yrs.cost as "Расчётные расходы, ₽",
    yrs.orders_sum as "Выручка, ₽",
    yrs.advert_id as "ID кампаний",
    yrs.name_advert as "Названия кампаний",
    yrs.actual_cost as "Фактические расходы, ₽",
    c.entrepreneur as "ИП"
FROM ya_report_shows_view yrs
LEFT JOIN clients c ON c.client_id = yrs.client_id
ORDER BY yrs.date DESC, c.entrepreneur, yrs.vendor_code
""", con=engine)

write_data(worksheet=get_worksheet(sheet_name='AdvBI', cols=len(df_ya_report_shows_view.columns) + 5),
           dataframe=df_ya_report_shows_view)

df_ya_report_consolidated = pd.read_sql("""
SELECT
    yrc.date as "Дата",
    yrc.vendor_code as "Ваш SKU",
    yrc.name_product as "Название товара",
    yrc.boost_shows as "Показы с бустом, шт.",
    yrc.total_shows as "Все показы, шт.",
    yrc.boost_clicks as "Клики с бустом, шт.",
    yrc.total_clicks as "Все клики, шт.",
    yrc.boost_add_to_card as "В корзину с бустом, шт.",
    yrc.total_add_to_card as "Все добавления в корзину, шт.",
    yrc.boost_orders_count as "Заказанные с бустом, шт.",
    yrc.total_orders_count as "Все заказанные, шт.",
    yrc.boost_orders_delivered_count as "Доставленные с бустом, шт.",
    yrc.total_orders_delivered_count as "Всего доставлено, шт.",
    yrc.cost as "Расходы на буст, ₽",
    yrc.bonus_cost as "Списано бонусов",
    yrc.average_cost as "Средняя стоимость буста, ₽",
    yrc.boost_revenue_ratio_cost / 100 as "Расходы на буст/Выручки с бустом, %%",
    yrc.boost_orders_delivered_sum as "Выручка с бустом, ₽",
    yrc.total_orders_delivered_sum as "Вся выручка, ₽",
    yrc.revenue_ratio_boost_total / 100 as "Выручка с бустом/Вся выручка, %%",
    yrc.advert_id as "ID кампаний",
    yrc.name_advert as "Названия кампаний",
    c.entrepreneur as "ИП"
FROM ya_report_consolidated yrc
LEFT JOIN clients c ON c.client_id = yrc.client_id
ORDER BY yrc.date DESC, c.entrepreneur, yrc.vendor_code
""", con=engine)

write_data(worksheet=get_worksheet(sheet_name='AdvBS', cols=len(df_ya_report_consolidated.columns) + 5),
           dataframe=df_ya_report_consolidated)

df_ya_report_shelf_view = pd.read_sql("""
SELECT
    yrs.date as "Дата",
    yrs.advert_id as "ID кампании",
    yrs.name_advert as "Название кампании",
    yrs.category as "Категория показа",
    yrs.shows as "Показы, шт.",
    yrs.coverage as "Охват, чел.",
    yrs.clicks as "Клики, шт.",
    yrs.ctr / 100 as "CTR, %%",
    yrs.shows_frequency as "Частота показа",
    yrs.add_to_card as "Добавления в корзину, шт.",
    yrs.orders_count as "Заказанные товары, шт.",
    yrs.orders_conversion / 100 as "Конверсия в заказы, %%",
    yrs.order_sum as "Стоимость заказанных товаров, ₽",
    yrs.cpo as "СРО, ₽",
    yrs.average_cost_per_mille as "Средняя ставка за 1000 показов, ₽",
    yrs.cost as "Расчётные расходы, ₽",
    yrs.cpm as "CPM, ₽",
    yrs.cost_ratio_revenue / 100 as "Расчётные расходы/Выручка, %%",
    yrs.actual_cost as "Фактические расходы, ₽",
    c.entrepreneur as "ИП"
FROM ya_report_shelf_view yrs
LEFT JOIN clients c ON c.client_id = yrs.client_id
WHERE yrs.date >= '2025-04-01'
ORDER BY yrs.date DESC, c.entrepreneur, yrs.advert_id, yrs.category
""", con=engine)

write_data(worksheet=get_worksheet(sheet_name='AdvS', cols=len(df_ya_report_shelf_view.columns) + 5),
           dataframe=df_ya_report_shelf_view)

df_cost_price = pd.read_sql("""
SELECT
    "month_date" as "Месяц",
    "year_date" as "Год",
    vendor_code as "Артикул",
    cost as "Себестоимость, ₽"
FROM cost_price
WHERE ("month_date" > 3 AND "year_date" = 2025) OR "year_date" > 2025
ORDER BY "year_date" DESC, "month_date" DESC, vendor_code
""", con=engine)

write_data(worksheet=get_worksheet(sheet_name='Sebes', cols=len(df_cost_price.columns) + 5),
           dataframe=df_cost_price)


df_ya_orders2 = pd.read_sql("""
SELECT
    yo.order_date AS "Дата заказа",
    c.entrepreneur AS "ИП",
    yr.vendor_code AS "Артикул",
    COUNT(distinct yr.posting_number) AS "Количество заказов",
    SUM(CASE WHEN yr.operation_type = 'Размещение товаров на витрине' THEN yr.cost ELSE 0 END) AS "Размещение на витрине",
    SUM(CASE WHEN yr.operation_type = ANY(ARRAY['Доставка покупателю', 'Экспресс-доставка покупателю']) THEN yr.cost ELSE 0 END) AS "Логистика",
    SUM(CASE WHEN yr.operation_type = ANY(ARRAY['Приём платежа', 'Перевод платежа']) THEN yr.cost ELSE 0 END) AS "Обработка платежа",
    COUNT(DISTINCT yr.posting_number) FILTER (WHERE yr.operation_type = 'Буст продаж, оплата за продажи') AS "Количество заказов с бустом",
    SUM(CASE WHEN yr.operation_type = 'Буст продаж, оплата за продажи' THEN yr.cost ELSE 0 END) AS "Буст продаж",
    COUNT(DISTINCT yr.posting_number) FILTER (WHERE yr.operation_type = 'Программа лояльности и отзывы') AS "Количество заказов с программой",
    SUM(CASE WHEN yr.operation_type = 'Программа лояльности и отзывы' THEN yr.cost ELSE 0 END) AS "Программа лояльности и отзывы"
FROM ya_report yr
LEFT JOIN ya_orders yo ON yr.posting_number = yo.posting_number
LEFT JOIN clients c ON c.client_id = yr.client_id
WHERE yo.status = 'DELIVERED'
AND yr.operation_type = ANY(ARRAY['Размещение товаров на витрине',
                                  'Буст продаж, оплата за продажи',
                                  'Доставка покупателю',
                                  'Приём платежа',
                                  'Перевод платежа',
                                  'Программа лояльности и отзывы'])
AND yr.service <> ALL(ARRAY['Доставка невыкупов и возвратов', 'Размещение товара (отмена по вине продавца)'])
AND yo.order_date >= '2025-04-01'
GROUP BY yo.order_date, c.entrepreneur, yr.vendor_code
ORDER BY yo.order_date DESC, c.entrepreneur, yr.vendor_code
""", con=engine)

write_data(worksheet=get_worksheet(sheet_name='Orders', cols=len(df_ya_orders2.columns) + 5),
           dataframe=df_ya_orders2)


df_clients = pd.read_sql("""
SELECT
    c.entrepreneur AS "ИП",
    c.tax_type AS "Схема налогообложения"
FROM clients c
WHERE c.marketplace = 'Yandex'
ORDER BY c.entrepreneur
""", con=engine)

write_data(worksheet=get_worksheet(sheet_name='TaxType', cols=len(df_ya_orders2.columns) + 5),
           dataframe=df_clients)
