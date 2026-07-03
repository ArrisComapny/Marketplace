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
SPREADSHEET_ID1 = '1DehtcP1a4OjDxMtqXPNRvosz2-62-PY3abHEKLz7q5g' # остатки\закуп
SPREADSHEET_ID2 = '17gKGe2ILkr7MV9VRDRWPcknSbHcNPdOGRa0cWQSffds' # Ежедневные заказы


# === Подключение к API Google Sheets ===
def connect_to_google_sheets(spreadsheet_id: str):
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
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

def get_column_map(header_row):
    return {name.strip(): idx for idx, name in enumerate(header_row) if name.strip()}


def get_cell(row, col_map, col_name, default=''):
    idx = col_map.get(col_name)
    if idx is None or idx >= len(row):
        return default
    return row[idx].strip()


def find_header_row(data, required_columns):
    for i, row in enumerate(data):
        normalized_row = [cell.strip() for cell in row]
        if all(col in normalized_row for col in required_columns):
            return i
    return None


def add_supply(db_conn: DbConnection):
    list_supplies = []
    vendors = set(db_conn.get_vendors())

    spreadsheet = connect_to_google_sheets(SPREADSHEET_ID2)
    sheet_name = "Шаблон"

    logger.info(f"Считываем данные с листа: {sheet_name}")

    worksheet = spreadsheet.worksheet(sheet_name)

    data = worksheet.get_all_values()

    required_columns = ['Offer_id', 'Комментарий', 'Кол-во', 'Дата прихода']
    header_index = find_header_row(data, required_columns)
    if header_index is None:
        raise Exception("Не найдена строка заголовков")

    header = data[header_index]
    col_map = get_column_map(header)

    for row in data[header_index + 1:]:
        offer_id = get_cell(row, col_map, 'Offer_id')
        comment = get_cell(row, col_map, 'Комментарий')
        quantity_col = get_cell(row, col_map, 'Кол-во')
        arrival_date_col = get_cell(row, col_map, 'Дата прихода')

        vendor_code = offer_id.strip().lower()

        for suffix in ['/m', '/м', '/s', '/l', '/xs', '/xl', '/2xl']:
            if vendor_code.endswith(suffix):
                vendor_code = vendor_code.removesuffix(suffix)
                break

        if not vendor_code or vendor_code not in vendors:
            continue

        if not comment and not quantity_col and not arrival_date_col:
            continue

        matches = re.findall(r"(\d+)\s+(\d{2}\.\d{2}\.\d{4})", comment)

        if matches:
            for quantity_str, date_str in matches:
                try:
                    quantity = int(quantity_str)
                    arrival_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                except ValueError:
                    continue

                list_supplies.append(
                    DataSupply(
                        date=arrival_date,
                        vendor_code=vendor_code,
                        supplies=quantity
                    )
                )

        else:
            quantity = None
            arrival_date = None

            if quantity_col:
                try:
                    quantity = int(quantity_col)
                except ValueError:
                    quantity = None

            if arrival_date_col:
                arrival_date = sheets_date_to_date(arrival_date_col)

            if quantity is None or arrival_date is None:
                continue

            list_supplies.append(
                DataSupply(
                    date=arrival_date,
                    vendor_code=vendor_code,
                    supplies=quantity
                )
            )

    # Агрегация данных для таблицы DataSupply
    aggregate_supply = {}
    for row in list_supplies:
        key = (row.date, row.vendor_code)

        if key not in aggregate_supply:
            aggregate_supply[key] = {"quantity": 0}

        aggregate_supply[key]["quantity"] += row.supplies

    list_supplies = []
    for key, values in aggregate_supply.items():
        arrival_date, vendor_code = key
        list_supplies.append(
            DataSupply(
                date=arrival_date,
                vendor_code=vendor_code,
                supplies=values["quantity"]
            )
        )

    # for key, values in aggregate_supply.items():
    #     print(key, values)
    logger.info(f'Количество записей: {len(list_supplies)}')

    db_conn.add_supplies(list_supplies=list_supplies)

def _collect_dated_sheets(spreadsheet) -> list[tuple[date, str]]:
    """Возвращает (sheet_date, original_title) для всех датированных листов остатков/закупа."""
    pattern = re.compile(r"\d{2}\.\d{2}\.\d{4}")
    result = []
    for ws in spreadsheet.worksheets():
        original = ws.title  # без strip — могут быть значимые пробелы/нбсп
        match = pattern.search(original)
        if not match or 'заказ' in original.lower():
            continue
        try:
            d = datetime.strptime(match.group(), "%d.%m.%Y").date()
            result.append((d, original))
        except ValueError:
            continue
    return result


def _parse_fbs_sheet(data: list[list[str]], sheet_date: date, vendors) -> list[DataCommodityAsset]:
    """Разбирает get_all_values() листа остатков и формирует список DataCommodityAsset."""
    header_index = find_header_row(data, ['Артикул', 'FBS', 'Кол-во'])
    if header_index is None:
        raise Exception("Не найдена строка заголовков с колонками 'Артикул', 'FBS', 'Кол-во'")

    col_map = get_column_map(data[header_index])
    art_idx = col_map['Артикул']
    fbs_idx = col_map['FBS']
    qty_idx = col_map['Кол-во']
    min_len = max(art_idx, fbs_idx, qty_idx) + 1

    list_assets = []
    for row in data[header_index + 1:]:
        if len(row) < min_len:
            continue

        vendor_code = row[art_idx].strip().lower()
        for suffix in ['/m', '/м', '/s', '/l', '/xs', '/xl', '/2xl']:  # Удаляем размер
            if vendor_code.endswith(suffix):
                vendor_code = vendor_code.removesuffix(suffix)
                break

        if vendor_code not in vendors:
            continue

        try:
            fbs = int(row[fbs_idx].strip())
            if fbs <= 0:
                fbs = 0
        except ValueError:
            fbs = 0

        try:
            quantity = int(row[qty_idx].strip())
            if quantity <= 0:
                quantity = 0
        except ValueError:
            quantity = 0

        if not fbs and not quantity:
            continue

        list_assets.append(DataCommodityAsset(vendor_code=vendor_code,
                                              fbs=fbs,
                                              on_the_way=quantity,
                                              date=sheet_date))
    return list_assets


def add_fbs_stocks(db_conn: DbConnection) -> None:
    vendors = db_conn.get_vendors()
    today = date.today()

    spreadsheet = connect_to_google_sheets(SPREADSHEET_ID1)
    dates_sheet_names = _collect_dated_sheets(spreadsheet)

    if not dates_sheet_names:
        logger.warning("Не найдено листов с датой — пропускаю обновление FBS-остатков")
        return

    # выбираем лист с самой поздней датой
    latest_date, name_list = max(dates_sheet_names, key=lambda x: x[0])

    # Свежесть: лист должен быть не старше 7 дней (включает текущую неделю + понедельник до нового вторника).
    age_days = (today - latest_date).days
    if age_days > 7:
        logger.warning(
            f"Самый свежий лист устарел: {latest_date} (возраст {age_days} дн.). "
            f"Пропускаю обновление FBS-остатков."
        )
        return

    logger.info(f"Считываем данные с листа: {name_list}")

    worksheet = spreadsheet.worksheet(name_list)
    data = worksheet.get_all_values()
    list_assets = _parse_fbs_sheet(data, latest_date, vendors)
    db_conn.add_commodity_assets(list_assets=list_assets)


def backfill_fbs_stocks(db_conn: DbConnection, from_date: date) -> None:
    """Догружает FBS-остатки и 'в пути' за все недели после from_date (строго больше)."""
    vendors = db_conn.get_vendors()

    spreadsheet = connect_to_google_sheets(SPREADSHEET_ID1)
    dates_sheet_names = _collect_dated_sheets(spreadsheet)

    targets = sorted([t for t in dates_sheet_names if t[0] > from_date], key=lambda x: x[0])
    if not targets:
        logger.info(f"Нет листов с датой строго после {from_date}")
        return

    logger.info(f"Будет обработано листов: {len(targets)}")
    for sheet_date, name in targets:
        logger.info(f"  {sheet_date}  ::  {name!r}")

    for sheet_date, name in targets:
        logger.info(f"Считываем данные с листа: {name} (дата {sheet_date})")
        worksheet = spreadsheet.worksheet(name)
        data = worksheet.get_all_values()
        list_assets = _parse_fbs_sheet(data, sheet_date, vendors)
        logger.info(f"  записей к загрузке: {len(list_assets)}")
        db_conn.add_commodity_assets(list_assets=list_assets)


def main_fbs_stocks(retries: int = 6) -> None:
    try:
        db_conn = DbConnection()
        db_conn.start_db()

        add_fbs_stocks(db_conn=db_conn)
        add_supply(db_conn=db_conn)
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            time.sleep(10)
            main_fbs_stocks(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    main_fbs_stocks()
