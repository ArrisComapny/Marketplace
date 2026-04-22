import os
import gspread
import logging
import datetime
import warnings

from gspread.utils import ValueRenderOption
from sqlalchemy import create_engine, text
from oauth2client.service_account import ServiceAccountCredentials

from config import DB_ARRIS_MASTER_URL, SPREADSHEET_ID

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
PATH_JSON = os.path.join(PROJECT_ROOT, 'templates', 'service-account-432709-1178152e9e49.json')

all_list = {
    'OZON 1': [4, 0, 10, 'Ozon', 2, 3, 5, 6],
    'OZON 2': [4, 0, 10, 'Ozon', 2, 3, 5, 6],
    'WB 3':   [4, 0, 9,  'WB', 2, 3, 5, 6],
    'YANDEX': [4, 0, 10, 'Yandex', 2, 3, 5, 6]
}

column = ['client_id', 'order_date', 'accrual_date', 'vendor_code', 'sku', 'quantities', 'price']


def get_values(sheet_name: str, to_date: datetime.date) -> list:
    creds = ServiceAccountCredentials.from_json_keyfile_name(PATH_JSON, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    worksheet = spreadsheet.worksheet(sheet_name)

    values = []

    data = worksheet.get_all_values(value_render_option=ValueRenderOption.unformatted)

    data = [d for d in data if d[0]]

    for row in data:
        try:
            accrual_date = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(row[all_list[sheet_name][0]])))
            if accrual_date < to_date:
                continue
            order_date = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(row[all_list[sheet_name][1]])))
            entrepreneur = row[all_list[sheet_name][2]].lower().strip()
            marketplace = all_list[sheet_name][3].lower().strip()
            vendor_code = str(row[all_list[sheet_name][4]]).lower().strip()
            sku = str(row[all_list[sheet_name][5]]).strip()
            quantities = int(row[all_list[sheet_name][6]])
            price = round(float(row[all_list[sheet_name][7]]), 2)

            if marketplace == 'wb' and entrepreneur.startswith('#'):
                if row[1] == 'Magasin':
                    entrepreneur = 'авагян г.г.'
                elif row[1] == 'SELLER':
                    entrepreneur = 'авагян в.г.'

            values.append([accrual_date, order_date, entrepreneur, marketplace, vendor_code, sku, quantities, price])
        except:
            pass

    return values


def self_purchase():
    to_date = datetime.date.today() - datetime.timedelta(days=20)

    entry = []
    final = []

    engine = create_engine(DB_ARRIS_MASTER_URL)

    logger.info(f'Получаю данные из БД')

    products_map = {}
    clients_map = {}

    with engine.connect() as conn:
        products = conn.execute(text("SELECT marketplace, sku, vendor_code, client_id FROM public.products_master"))
        for product in products.fetchall():
            marketplace = product[0].lower()
            products_map.setdefault(marketplace, {})
            if marketplace == 'yandex':
                products_map[marketplace][product[2]] = (product[3], product[1])
            else:
                products_map[marketplace][product[1]] = (product[3], product[2])

        clients = conn.execute(text("SELECT client_id, marketplace, entrepreneur FROM public.clients_master"))
        for c in clients.fetchall():
            clients_map.setdefault((c[1].lower(), c[2].lower()), c[0])
    logger.info(f'Данные по товарам получены')

    logger.info(f'Сбор данных по самовыкупам за период от {to_date.isoformat()}')

    for sheet_name, indexes in all_list.items():
        try:
            logger.info(f'Сбор данных таблицы {sheet_name} начат')
            values = get_values(sheet_name=sheet_name, to_date=to_date)
            entry.extend(values)
            logger.info(f'Сбор данных таблицы {sheet_name} выполнен, количество записей: {len(values)}')
        except Exception as e:
            raise Exception(f'Ошибка сбора данных таблицы {sheet_name}: {str(e)}')

    logger.info(f'Сбор данных завершен, количество записей: {len(entry)}')

    for row in entry:
        if any((not r) or (isinstance(r, str) and r.lower().startswith('#n/a')) for r in row):
            continue
        try:
            accrual_date, order_date, entrepreneur, marketplace, vendor_code, sku, quantities, price = row
            if marketplace == 'yandex':
                client_id, sku = products_map[marketplace][vendor_code]
            else:
                client_id, vendor_code = products_map[marketplace][sku]
                if client_id == '25473' and entrepreneur != 'Антон':
                    client_id = clients_map.get((marketplace.lower(), entrepreneur.lower())) or client_id

            final.append([client_id, order_date, accrual_date, vendor_code, sku, quantities, price])
        except Exception as e:
            logger.error(f'Ошибка в опознании товара {row}: {str(e)}')

    rows = [dict(zip(column, row)) for row in final]

    if not rows:
        raise Exception("Нет данных")

    delete_sql = text("""
        DELETE FROM public.self_purchase_master
        WHERE accrual_date >= :to_date
    """)

    insert_sql = text("""
        INSERT INTO public.self_purchase_master
            (client_id, order_date, accrual_date, vendor_code, sku, quantities, price)
        VALUES
            (:client_id, :order_date, :accrual_date, :vendor_code, :sku, :quantities, :price)
    """)

    with engine.begin() as conn:
        logger.info(f'Удаляю записи из self_purchase_master от {to_date.isoformat()}')
        conn.execute(delete_sql, {'to_date': to_date})
        logger.info('Вставляю новые записи в self_purchase_master')
        conn.execute(insert_sql, rows)
        logger.info('Запись успешно завершена')


try:
    self_purchase()
except Exception as e:
    logger.error(str(e))
