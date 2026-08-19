import os
import re
import gspread
import logging
import datetime
import warnings

from sqlalchemy import create_engine, text
from oauth2client.service_account import ServiceAccountCredentials

from config import DB_URL

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
PATH_JSON = os.path.join(PROJECT_ROOT, 'templates', 'service-account-432709-1178152e9e49.json')
PROJECT = 'Расчет себестоимости'
PROJECT_MARKET = 'Arris - ТОВАРЫ РЫНОК'

month = {
    1: 'январь',
    2: 'февраль',
    3: 'март',
    4: 'апрель',
    5: 'май',
    6: 'июнь',
    7: 'июль',
    8: 'август',
    9: 'сентябрь',
    10: 'октябрь',
    11: 'ноябрь',
    12: 'декабрь'
}

column = ['accrual_date', 'vendor_code', 'quantities', 'price', 'log_cost', 'log_add_cost']


def get_values_china(to_date: datetime.date) -> list:
    sheet_name = 'Китай приемка'

    creds = ServiceAccountCredentials.from_json_keyfile_name(PATH_JSON, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open(PROJECT)

    worksheet = spreadsheet.worksheet(sheet_name)

    data = worksheet.get_all_values()

    to_year = to_date.year
    index = next((i for i, sublist in enumerate(data) if sublist[0] == str(to_year)), None)
    data = data[index:]

    to_month = to_date.month
    index = next((i for i, sublist in enumerate(data) if sublist[0].lower().strip() == month.get(to_month)), None)
    data = data[index:]

    list_except = list(month.values()) + ['наименование', 'артикул', 'наименовение']
    data = [sublist for sublist in data if sublist[0].lower().strip() not in list_except and sublist[0].strip()]

    entry = []
    date_obj = None

    for val in data:
        if val[0].startswith('Приемка'):
            try:
                date_str = val[0].split()[-1]
                date_obj = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
                if date_obj < to_date:
                    date_obj = None
            except Exception as e:
                logger.error(f'Ошибка форматирование даты {val[0]}: {str(e)}')
                date_obj = None
        elif date_obj and len(val) > 8:
            try:
                vendor_code = val[0].lower().strip()
                quantities = int(val[2])
                price = round(float(val[3].replace(',', '.')), 2)
                log_cost = round(float(val[6].replace(',', '.')), 2)
                log_add_cost = round(float(val[8].replace(',', '.')), 2) if val[8] else 0

                index = next((i for i, sublist in enumerate(entry) if sublist[0:2] == [date_obj, vendor_code]), None)
                if index is not None:
                    entry.pop(index)

                entry.append([date_obj, vendor_code, quantities, price, log_cost, log_add_cost])
            except Exception as e:
                logger.error(f'Ошибка форматирования данных {val}: {str(e)}')

    return [dict(zip(column, row)) for row in entry]


def get_values_russia(to_date: datetime.date) -> list:
    sheet_name = 'себес белая'

    creds = ServiceAccountCredentials.from_json_keyfile_name(PATH_JSON, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open(PROJECT)

    worksheet = spreadsheet.worksheet(sheet_name)

    data = worksheet.get_all_values()

    entry = []

    for val in data:
        if len(val) >= 34 and val[0].strip():
            try:
                if val[34] != 'TRUE':
                    continue
                date_obj = datetime.datetime.strptime(val[2].strip(), "%d.%m.%Y").date()
                if date_obj < to_date:
                    continue

                vendor_code = val[0].lower().strip()
                quantities = int(val[7])
                price = round(float(val[10].replace(',', '.')), 2)
                log_cost = round(float(val[19].replace(',', '.') or 0), 2)
                if log_cost == 0:
                    log_cost_rub = round(float(val[21].replace(',', '.') or 0), 2)
                else:
                    log_cost_rub = 0

                commission_cost = float(val[17].replace(',', '.') or 0)
                auto_pickup = float(val[22].replace(',', '.') or 0)
                terminal_expenses = float(val[23].replace(',', '.') or 0)
                customs_clearance = float(val[24].replace(',', '.') or 0)
                delay = float(val[25].replace(',', '.') or 0)
                customs_duties = float(val[26].replace(',', '.') or 0)
                certification = float(val[31].replace(',', '.') or 0)
                log_add_cost = round(
                    log_cost_rub + commission_cost + auto_pickup + terminal_expenses + customs_clearance + delay + customs_duties + certification, 2)

                entry.append([date_obj, vendor_code, quantities, price, log_cost, log_add_cost])
            except Exception as e:
                logger.error(f'Ошибка форматирования данных {val}: {str(e)}')

    return [dict(zip(column, row)) for row in entry]

def aggregate_rows(rows: list) -> list:
    aggregated = {}

    for row in rows:
        key = (row['accrual_date'], row['vendor_code'])

        if key in aggregated:
            old_qty = aggregated[key]['quantities']
            old_price = aggregated[key]['price']
            new_qty = old_qty + row['quantities']

            # средневзвешенная цена
            new_price = round(
                ((old_qty * old_price) + (row['quantities'] * row['price'])) / new_qty,
                2
            )

            aggregated[key]['quantities'] = new_qty
            aggregated[key]['price'] = new_price
            aggregated[key]['log_cost'] = round(aggregated[key]['log_cost'] + row['log_cost'], 2)
            aggregated[key]['log_add_cost'] = round(aggregated[key]['log_add_cost'] + row['log_add_cost'], 2)
        else:
            aggregated[key] = row.copy()

    return list(aggregated.values())

def get_values_market(to_date: datetime.date) -> list:
    start_date = datetime.date(2026, 6, 2)
    if to_date < start_date:
        to_date = start_date
    sheet_name = 'Приемки'

    creds = ServiceAccountCredentials.from_json_keyfile_name(PATH_JSON, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open(PROJECT_MARKET)

    worksheet = spreadsheet.worksheet(sheet_name)

    data = worksheet.get_all_values()

    entry = []

    for val in data:
        if len(val) >= 9 and all(val[i].strip() for i in (0, 1, 7, 8)):
            try:
                date_obj = datetime.datetime.strptime(val[0].strip(), "%d.%m.%Y").date()

                if date_obj < to_date:
                    continue

                vendor_code = val[1].lower().strip()
                quantities = int(re.sub(r'[^\d,-]', '', val[7]))
                cleaned_price = re.sub(r'[^\d,]', '', val[8])
                price = round(float(cleaned_price.replace(',', '.')), 2)
                entry.append([date_obj, vendor_code, quantities, price])
            except Exception as e:
                logger.error(f'Ошибка форматирования данных {val}: {str(e)}')

    market_columns = ['accrual_date', 'vendor_code', 'quantities', 'price']
    return [dict(zip(market_columns, row)) for row in entry]


def overseas_purchase():
    to_date = datetime.date.today() - datetime.timedelta(days=90)

    values_china = get_values_china(to_date=to_date)
    values_russia = get_values_russia(to_date=to_date)
    values_market = get_values_market(to_date=to_date)

    rows = values_china + values_russia
    rows = aggregate_rows(rows)

    if not rows:
        logger.warning('Данные по поставкам отсутствуют')
        return

    for row in rows:
        print(row)

    engine = create_engine(DB_URL)

    delete_sql = text("""
        DELETE FROM public.overseas_purchase
        WHERE accrual_date >= :to_date
    """)

    insert_sql = text("""
        INSERT INTO public.overseas_purchase
            (accrual_date, vendor_code, quantities, price, log_cost, log_add_cost)
        VALUES
            (:accrual_date, :vendor_code, :quantities, :price, :log_cost, :log_add_cost)
        ON CONFLICT (accrual_date, vendor_code) DO UPDATE
        SET
            quantities = EXCLUDED.quantities,
            price = EXCLUDED.price,
            log_cost = EXCLUDED.log_cost,
            log_add_cost = EXCLUDED.log_add_cost
    """)

    delete_market_sql = text("""
        DELETE FROM public.overseas_purchase_market
        WHERE accrual_date >= :to_date
    """)

    insert_sql_market = text("""
        INSERT INTO public.overseas_purchase_market
            (accrual_date, vendor_code, quantities, price)
        VALUES
            (:accrual_date, :vendor_code, :quantities, :price)
    """)

    with engine.begin() as conn:
        logger.info(f'Удаляю записи из overseas_purchase от {to_date.isoformat()}')
        conn.execute(delete_sql, {'to_date': to_date})
        logger.info('Вставляю новые записи в overseas_purchase')
        conn.execute(insert_sql, rows)
        logger.info('Запись успешно завершена')
        logger.info(f'Удаляю записи из overseas_purchase_market от {to_date.isoformat()}')
        conn.execute(delete_market_sql, {'to_date': to_date})
        logger.info('Вставляю новые записи в overseas_purchase_market')
        if values_market:
            conn.execute(insert_sql_market, values_market)
            logger.info('Запись успешно завершена')
        else:
            logger.warning('Нет данных по рынку — пропускаю вставку в overseas_purchase_market')


try:
    overseas_purchase()
except Exception as e:
    logger.error(str(e))
