import os
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


def overseas_purchase():
    to_date = datetime.date.today() - datetime.timedelta(days=30)

    values_china = get_values_china(to_date=to_date)
    values_russia = get_values_russia(to_date=to_date)

    rows = values_china + values_russia

    if not rows:
        logger.warning('Данные по поставкам отсутствуют')
        return

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

    with engine.begin() as conn:
        logger.info(f'Удаляю записи из overseas_purchase от {to_date.isoformat()}')
        conn.execute(delete_sql, {'to_date': to_date})
        logger.info('Вставляю новые записи в overseas_purchase')
        conn.execute(insert_sql, rows)
        logger.info('Запись успешно завершена')


try:
    overseas_purchase()
except Exception as e:
    logger.error(str(e))
