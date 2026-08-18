import os
import re
import time
import gspread
import logging
import datetime
import warnings

from collections import Counter
from sqlalchemy.exc import OperationalError
from oauth2client.service_account import ServiceAccountCredentials

from database import DbConnection
from data_classes import DataInventory

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
PATH_JSON = os.path.join(PROJECT_ROOT, 'templates', 'service-account-432709-1178152e9e49.json')
PROJECT = 'Расчет себестоимости'

SPREADSHEET_ID = '1dMmJwNA91lCKv8VFlzh3RQ-NbARUC6XTvs3dNiUwpEY'
SHEET_NAME = 'Инвентаризация склад'
CATALOG_SHEET_NAME = 'Каталог'
FBS_SHEET_NAME = 'Инвентаризация FBS'
FBS_HEADER = ['Номер', 'Дата', 'ИП', 'Артикул', 'Кол-во']


def connect_to_google_sheets(spreadsheet_id: str):
    creds = ServiceAccountCredentials.from_json_keyfile_name(PATH_JSON, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet


def get_inventory_data(spreadsheet, sheet_name: str = SHEET_NAME) -> list[list[str]]:
    """Читает все значения с листа инвентаризации."""
    logger.info(f'Считываем данные с листа: {sheet_name}')

    worksheet = spreadsheet.worksheet(sheet_name)
    data = worksheet.get_all_values()

    logger.info(f'Получено строк: {len(data)}')
    return data


def _rewrite_sheet(worksheet, rows: list[list], first_row: int = 2) -> None:
    """Чистит значения листа с first_row и пишет заново. Оформление не трогает."""
    need_rows = len(rows) + first_row - 1
    if worksheet.row_count < need_rows:
        worksheet.add_rows(need_rows - worksheet.row_count)

    # batch_clear чистит только значения, форматирование остаётся
    worksheet.batch_clear([f'A{first_row}:E{worksheet.row_count}'])

    if rows:
        worksheet.update(values=rows, range_name=f'A{first_row}', value_input_option='RAW')


def update_catalog_sheet(spreadsheet, db_conn: DbConnection) -> None:
    """Выгружает ip_vendor_code в лист 'Каталог'."""
    rows = [
        ['' if cell is None else str(cell) for cell in row]
        for row in db_conn.get_ip_vendor_codes()
    ]

    logger.info(f'Выгружаем в лист {CATALOG_SHEET_NAME}: {len(rows)} строк')

    # первая строка — заголовки, данные с A2
    _rewrite_sheet(spreadsheet.worksheet(CATALOG_SHEET_NAME), rows, first_row=2)

    logger.info(f'Лист {CATALOG_SHEET_NAME} обновлён')


def update_fbs_sheet(spreadsheet, db_conn: DbConnection) -> None:
    """Выгружает представление inventory_stocks в лист 'Инвентаризация FBS'."""
    rows = [
        [
            int(id_inventory),
            row_date.strftime('%d.%m.%Y'),
            entrepreneur,
            vendor_code,
            quantity
        ]
        for id_inventory, row_date, entrepreneur, vendor_code, quantity in db_conn.get_inventory_stocks()
    ]

    logger.info(f'Выгружаем в лист {FBS_SHEET_NAME}: {len(rows)} строк')

    worksheet = spreadsheet.worksheet(FBS_SHEET_NAME)

    # шапку пишем сами — лист заполняется целиком
    _rewrite_sheet(worksheet, [FBS_HEADER] + rows, first_row=1)

    # артикулы могут быть чисто цифровыми, поэтому весь блок пишем как RAW,
    # а номер и дату отдельно через USER_ENTERED — иначе останутся текстом
    if rows:
        worksheet.update(values=[row[:2] for row in rows],
                         range_name=f'A2:B{len(rows) + 1}',
                         value_input_option='USER_ENTERED')

    logger.info(f'Лист {FBS_SHEET_NAME} обновлён')


def _parse_int(value: str) -> int:
    """'2\xa0343' -> 2343. Убираем любые пробелы-разделители тысяч."""
    return int(re.sub(r'\s', '', value.replace('\xa0', '')))


def _parse_bool(value: str) -> bool:
    value = value.strip().upper()
    if value in ('TRUE', 'ИСТИНА', '1', 'ДА'):
        return True
    if value in ('FALSE', 'ЛОЖЬ', '0', 'НЕТ'):
        return False
    raise ValueError(f'Не булево значение: {value!r}')


def parse_inventory_rows(data: list[list[str]]) -> list[DataInventory]:
    """Приводит строки листа к типам. Битые строки и некаталогизированные отбрасываются."""
    rows = []
    skipped_errors = 0
    skipped_not_catalogued = 0

    for i, row in enumerate(data[1:], start=2):
        if len(row) < 5:
            skipped_errors += 1
            continue

        id_inventory, date_str, vendor_code, quantity_str, catalogued_str = (cell.strip() for cell in row[:5])

        try:
            row_date = datetime.datetime.strptime(date_str, '%d.%m.%Y').date()
            quantity = _parse_int(quantity_str)
            catalogued = _parse_bool(catalogued_str)
        except ValueError as e:
            logger.debug(f'Строка {i} пропущена: {e}')
            skipped_errors += 1
            continue

        if not id_inventory or not vendor_code:
            skipped_errors += 1
            continue

        if not catalogued:
            skipped_not_catalogued += 1
            continue

        rows.append(
            DataInventory(
                id_inventory=id_inventory,
                date=row_date,
                vendor_code=vendor_code,
                quantity=quantity
            )
        )

    logger.info(f'Разобрано строк: {len(rows)}, '
                f'с ошибками: {skipped_errors}, не каталогизировано: {skipped_not_catalogued}')

    # В таблице inventory уникальны (date, vendor_code) — дублей в листе быть не должно
    counter = Counter((row.date, row.vendor_code) for row in rows)
    duplicates = {key for key, count in counter.items() if count > 1}

    if duplicates:
        logger.warning(f'Найдены дубли по (Дата, Артикул): {len(duplicates)} — количество суммируется, поправьте лист')
        for row_date, vendor_code in sorted(duplicates, key=lambda k: k[1]):
            quantities = [row.quantity for row in rows if (row.date, row.vendor_code) == (row_date, vendor_code)]
            logger.warning(f'  {row_date} {vendor_code}: {quantities} -> {sum(quantities)}')

    aggregate_inventory = {}
    for row in rows:
        key = (row.id_inventory, row.date, row.vendor_code)

        if key not in aggregate_inventory:
            aggregate_inventory[key] = 0

        aggregate_inventory[key] += row.quantity

    return [
        DataInventory(
            id_inventory=id_inventory,
            date=row_date,
            vendor_code=vendor_code,
            quantity=quantity
        )
        for (id_inventory, row_date, vendor_code), quantity in aggregate_inventory.items()
    ]


def main_inventory(retries: int = 6) -> None:
    try:
        db_conn = DbConnection()
        db_conn.start_db()

        spreadsheet = connect_to_google_sheets(SPREADSHEET_ID)

        # сначала выгружаем справочник артикулов из БД в лист 'Каталог'
        update_catalog_sheet(spreadsheet=spreadsheet, db_conn=db_conn)

        data = get_inventory_data(spreadsheet=spreadsheet)
        list_inventory = parse_inventory_rows(data)

        db_conn.add_inventory(list_inventory=list_inventory)

        # представление считает уже загруженные данные — выгружаем после записи в БД
        update_fbs_sheet(spreadsheet=spreadsheet, db_conn=db_conn)
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            time.sleep(10)
            main_inventory(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == '__main__':
    main_inventory()
