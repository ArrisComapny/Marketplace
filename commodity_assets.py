import re
import os
import time
import logging
import gspread

from sqlalchemy.exc import OperationalError
from datetime import datetime, date, timedelta
from oauth2client.service_account import ServiceAccountCredentials

from database import DbConnection
from data_classes import DataSupply, DataCommodityAsset

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(PROJECT_ROOT, 'templates', 'service-account-432709-1178152e9e49.json')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1DehtcP1a4OjDxMtqXPNRvosz2-62-PY3abHEKLz7q5g'


# === Подключение к API Google Sheets ===
def connect_to_google_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return spreadsheet


# === Получаем все названия листов ===
def get_sheet_names(spreadsheet):
    worksheets = spreadsheet.worksheets()
    sheet_names = [ws.title for ws in worksheets]
    return sheet_names


def sheets_date_to_date(value):
    if not value:  # если пусто
        return None

    # если значение похоже на число (Google Sheets может хранить дату как float)
    try:
        num = float(value)
        return (datetime(1899, 12, 30) + timedelta(days=num)).date()
    except ValueError:
        pass

    # пробуем строку в разных форматах
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None  # ничего не подошло


def add_fbs_stocks(db_conn: DbConnection) -> None:
    list_assets = []
    list_supplies = []

    vendors = db_conn.get_vendors()

    today = date.today()
    pattern = re.compile(r"\d{2}\.\d{2}\.\d{4}")
    spreadsheet = connect_to_google_sheets()
    sheet_names = get_sheet_names(spreadsheet)

    dates_sheet_names = []  # теперь тут (date, name)

    for name in sheet_names:
        name = name.strip()
        match = pattern.search(name)

        if match:
            try:
                date_obj = datetime.strptime(match.group(), "%d.%m.%Y").date()
                dates_sheet_names.append((date_obj, name))  # сохраняем и дату и имя
            except ValueError:
                pass

    if not dates_sheet_names:
        raise Exception("Не найдено листов с датой")

    # выбираем лист с самой поздней датой
    latest = max(dates_sheet_names, key=lambda x: x[0])

    latest_date = latest[0]  # сама дата
    name_list = latest[1]  # реальное название листа

    # Проверка недели
    if not (
            latest_date.isocalendar()[0] == today.isocalendar()[0] and
            latest_date.isocalendar()[1] == today.isocalendar()[1]
    ):
        print(latest_date)
        print(today)
        raise Exception("Invalid date")

    logger.info(f"Считываем данные с листа: {name_list}")

    # открываем лист по настоящему названию
    worksheet = spreadsheet.worksheet(name_list)
    data = worksheet.get_all_values()
    for row in data[2:]:
        if len(row) <= 52:
            continue

        vendor_code = row[1].strip().lower()
        for suffix in ['/m','/м','/s','/l','/xs','/xl','/2xl']:  # Удаляем  размер
            if vendor_code.endswith(suffix):
                vendor_code = vendor_code.removesuffix(suffix)
                break

        if vendor_code not in vendors:  # Проверка есть ли артикул в базе данных
            continue

        fbs_value = row[38].strip()
        try:
            fbs = int(fbs_value) # --- получаем fbs ---
            if fbs <= 0:
                fbs = 0
        except ValueError:
            fbs = 0

        quantity_value = row[49].strip()
        try:
            quantity = int(quantity_value)  # --- получаем quantity ---
            if quantity <= 0:
                quantity = 0
        except ValueError:
            quantity = 0

        if not fbs and not quantity:
            continue

        list_assets.append(DataCommodityAsset(vendor_code=vendor_code, fbs=fbs, on_the_way=quantity, date=latest_date))

        if quantity:
            orientation_arrival_value = row[51].strip()
            orientation_arrival = sheets_date_to_date(orientation_arrival_value) # Получаем дату через функцию.
            if orientation_arrival:
                list_supplies.append(DataSupply(date=orientation_arrival, vendor_code=vendor_code, supplies=quantity))

    # Агрегация данных для таблицы DataCommodityAsset
    # aggregate = {}
    # for row in list_assets:
    #     key = (
    #         row.date,
    #         row.vendor_code
    #     )
    #     if key not in aggregate:
    #         aggregate[key] = {"on_the_way": 0, "fbs": 0}
    #
    #     aggregate[key]["on_the_way"] += row.on_the_way
    #     aggregate[key]["fbs"] += row.fbs
    #
    # list_assets = []
    # for key, values in aggregate.items():
    #     latest, vendor_code = key
    #     list_assets.append(DataCommodityAsset(vendor_code=vendor_code,
    #                                           fbs=values['fbs'],
    #                                           on_the_way=values['on_the_way'],
    #                                           date=latest))

    # Агрегация данных для таблицы DataSupply
    aggregate_supply = {}
    for row in list_supplies:
        key = (
            row.date,
            row.vendor_code
        )
        if key not in aggregate_supply:
            aggregate_supply[key] = {"quantity": 0}

        aggregate_supply[key]["quantity"] += row.supplies

    list_supplies = []
    for key, values in aggregate_supply.items():
        orientation_arrival, vendor_code = key
        list_supplies.append(DataSupply(date=orientation_arrival,
                                        vendor_code=vendor_code,
                                        supplies=values['quantity']))

    logger.info(f'Количество записей: {len(list_assets)}')
    db_conn.add_commodity_assets(list_assets=list_assets)

    logger.info(f'Количество записей: {len(list_supplies)}')
    db_conn.add_supplies(list_supplies=list_supplies)


def main_fbs_stocks(retries: int = 6) -> None:
    try:
        db_conn = DbConnection()
        db_conn.start_db()

        add_fbs_stocks(db_conn=db_conn)
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            time.sleep(10)
            main_fbs_stocks(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    main_fbs_stocks()
