import os
import re
import time
from copy import copy

import gspread
import logging
import requests

from contextlib import suppress
from datetime import date, datetime, timedelta
from gspread.utils import ValueInputOption
from sqlalchemy.exc import OperationalError
from oauth2client.service_account import ServiceAccountCredentials

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from database import DbConnection

# Настройка
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

# Константы
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
PATH_JSON = os.path.join(PROJECT_ROOT, 'templates', 'service-account-432709-1178152e9e49.json')
PROJECT = 'Ежедневные заказы'
SAMPLE = 'Шаблон'
WEEK = 'Неделька'
TO_TODAY = 'ТО сегодня'
TO_MINUS_7 = 'ТО -7'

# Цветовые схемы
COLOR_HEADER2 = {"red": 0.69, "green": 0.93, "blue": 0.93}
COLOR_HEADER = {"red": 0.17, "green": 0.32, "blue": 0.51}  # тёмно-синий #2C5282 (с белым текстом)
COLOR_HEADER_TEXT = {"red": 1.00, "green": 1.00, "blue": 1.00}
COLOR_MARKET_DATA = {"red": 0.72, "green": 0.88, "blue": 0.8}
COLOR_FORMAT = {"red": 0.96, "green": 0.8, "blue": 0.8}
COLOR_MAIN_ROW = {"red": 0.93, "green": 0.95, "blue": 0.97}  # светлый сине-серый #EDF2F7
COLOR_ABC_A = {"red": 0.72, "green": 0.88, "blue": 0.80}  # светло-зелёный
COLOR_ABC_B = {"red": 1.00, "green": 0.94, "blue": 0.65}  # светло-жёлтый
COLOR_ABC_C = {"red": 0.96, "green": 0.80, "blue": 0.80}  # светло-красный
TAB_COLOR_NEW_SHEET = {"red": 0, "green": 1, "blue": 0.33}
TAB_COLOR_COPY_SHEET = {"red": 1, "green": 1, "blue": 0}
BORDER_STYLE = {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}}
COLOR_SECTION_TOTALS = {"red": 0.80, "green": 0.90, "blue": 1.00}  # пастельно-синий — секции Рынок/Китай


def column_to_letter(column: int):
    letters = []
    while column > 0:
        column, remainder = divmod(column - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(letters[::-1])


def get_column_cell_colors(spreadsheet_id: str, sheet_name: str, column_letter: str = 'A') -> dict:
    """Получение цветов ячеек из шаблона."""
    creds = Credentials.from_service_account_file(PATH_JSON, scopes=SCOPE)
    service = build('sheets', 'v4', credentials=creds, cache_discovery=False)

    range_ = f"{sheet_name}!{column_letter}2:{column_letter}1000"

    response = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=[range_],
        includeGridData=True
    ).execute()

    result = {'Остальное': {'red': 0.878, 'green': 0.878, 'blue': 0.878}}
    rows = response['sheets'][0]['data'][0].get('rowData', [])

    for row in rows:
        cell_data = row.get('values', [{}])[0]
        value = cell_data.get('formattedValue')
        color = cell_data.get('effectiveFormat', {}).get('backgroundColor')
        if value is not None and color is not None:
            result[value] = color

    return result


def keep_first_n_sheets(spreadsheet: gspread.Spreadsheet, n: int = 90):
    sheets = spreadsheet.worksheets()

    # Всегда сохраняем закреплённые листы: Шаблон, Неделька, ТО сегодня, ТО -7.
    keep = [SAMPLE, WEEK, TO_TODAY, TO_MINUS_7]

    filtered = [ws for ws in sheets if ws.title not in keep]

    # если больше n, удаляем лишние
    if len(filtered) > n:
        for ws in filtered[n:]:
            spreadsheet.del_worksheet(ws)


def reorder_sheets(spreadsheet: gspread.Spreadsheet) -> None:
    """Реорганизация листов: Шаблон, Неделька, ТО сегодня, ТО -7 — всегда первые
    4 в этом порядке; ТО-листы держим скрытыми. Дальше — даты по убыванию, оригинал
    перед своей копией."""
    worksheets = spreadsheet.worksheets()
    sheets = {ws.title: ws.id for ws in worksheets}

    # Закреплённые листы всегда в начале в фиксированном порядке.
    pinned = [SAMPLE, WEEK, TO_TODAY, TO_MINUS_7]

    desired_order = [t for t in sheets if t not in pinned]
    desired_order.sort(reverse=True, key=lambda x: (x.split(" копия")[0], "копия" not in x))
    desired_order = [t for t in pinned if t in sheets] + desired_order

    all_requests = []
    for index, sheet_name in enumerate(desired_order):
        sheet_id = sheets.get(sheet_name)
        if sheet_id is None:
            continue
        props = {"sheetId": sheet_id, "index": index}
        fields = "index"
        # ТО-листы держим скрытыми — они служебные, данные оттуда тянутся формулами.
        if sheet_name in (TO_TODAY, TO_MINUS_7):
            props["hidden"] = True
            fields = "index,hidden"
        all_requests.append({"updateSheetProperties": {"properties": props, "fields": fields}})

    if all_requests:
        spreadsheet.batch_update({"requests": all_requests})


def initialize_google_sheet() -> gspread.Spreadsheet:
    creds = ServiceAccountCredentials.from_json_keyfile_name(PATH_JSON, SCOPE)
    client = gspread.authorize(creds)
    return client.open(PROJECT)


def hide_and_rename_existing_sheet(spreadsheet: gspread.Spreadsheet, worksheet_name: str) -> None:
    with suppress(gspread.exceptions.WorksheetNotFound):
        try:
            existing_sheet = spreadsheet.worksheet(worksheet_name)
            spreadsheet.batch_update(
                {"requests": [{"updateSheetProperties": {"properties": {"sheetId": existing_sheet.id,
                                                                        "hidden": True,
                                                                        "title": f"{worksheet_name} копия",
                                                                        "tabColor": TAB_COLOR_COPY_SHEET},
                                                         "fields": "title,hidden,tabColor"}}]})
        except gspread.exceptions.APIError as e:
            if 'Please enter another name' in e.response.text:
                spreadsheet.del_worksheet(existing_sheet)


def format_sheet(worksheet: gspread.Worksheet, spreadsheet: gspread.Spreadsheet, data: list, col_map: dict,
                 cat_map: dict, marketplaces: list) -> None:
    vendor_colors = get_column_cell_colors(spreadsheet_id=spreadsheet.id, sheet_name='Шаблон')

    all_requests = []  # Список запросов на форматирование

    col_total_i = col_map["Итого"]["index"]
    col_total_stock_i = col_map["Итого остаток"]["index"]

    # Форматируем заголовки задаём цвет и выравниваем посередине
    all_requests.append({"repeatCell": {"range": {"sheetId": worksheet.id,
                                                  "startRowIndex": 0,
                                                  "endRowIndex": 2,
                                                  "endColumnIndex": len(data[1])},
                                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER",
                                                                       "verticalAlignment": "MIDDLE",
                                                                       "wrapStrategy": "WRAP",
                                                                       "backgroundColor": COLOR_HEADER2}},
                                        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment, "
                                                  "wrapStrategy,backgroundColor)"}})

    # Для остальных колонок задаём ширину
    all_requests.append({"updateDimensionProperties": {"range": {"sheetId": worksheet.id,
                                                                 "dimension": "COLUMNS",
                                                                 "startIndex": 1,
                                                                 "endIndex": col_total_stock_i},
                                                       "properties": {"pixelSize": 90},
                                                       "fields": "pixelSize"}})

    # Для каждой обязательной колонки задаём ширину
    for enum, header in enumerate([*data[1][0:2], *data[1][-5:]], 1):
        size = {1: 170,
                2: 130}
        all_requests.append({
            "updateDimensionProperties": {"range": {"sheetId": worksheet.id,
                                                    "dimension": "COLUMNS",
                                                    "startIndex": col_map[header]['index'] - 1,
                                                    "endIndex": col_map[header]['index']},
                                          "properties": {"pixelSize": size.get(enum, 100)},
                                          "fields": "pixelSize"}})

    # Задаём стиль границ для заголовков
    all_requests.append({"updateBorders": {"range": {"sheetId": worksheet.id,
                                                     "startRowIndex": 1,
                                                     "endRowIndex": 2,
                                                     "endColumnIndex": len(data[1])},
                                           "bottom": BORDER_STYLE,
                                           "left": BORDER_STYLE,
                                           "right": BORDER_STYLE,
                                           "innerVertical": BORDER_STYLE}})

    # Закрепляем заголовки и первые 1 столбеца
    all_requests.append({"updateSheetProperties": {"properties": {"sheetId": worksheet.id,
                                                                  "gridProperties": {"frozenRowCount": 2}},
                                                   "fields": "gridProperties.frozenRowCount"}})
    all_requests.append({"updateSheetProperties": {"properties": {"sheetId": worksheet.id,
                                                                  "gridProperties": {"frozenColumnCount": 1}},
                                                   "fields": "gridProperties.frozenColumnCount"}})

    # Задаём высоту первой строки
    all_requests.append({"updateDimensionProperties": {"range": {"sheetId": worksheet.id,
                                                                 "dimension": "ROWS",
                                                                 "startIndex": 1,
                                                                 "endIndex": 2},
                                                       "properties": {"pixelSize": 37},
                                                       "fields": "pixelSize"}})

    # Выравниваем по центру данные
    all_requests.append({"repeatCell": {"range": {"sheetId": worksheet.id,
                                                  "startRowIndex": 2,
                                                  "endColumnIndex": 1},
                                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat(horizontalAlignment)"}})
    all_requests.append({"repeatCell": {"range": {"sheetId": worksheet.id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 2,
                                                  "endColumnIndex": col_total_stock_i},
                                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat(horizontalAlignment)"}})

    # Для каждого маркетплейса группируем магазины
    for marketplace in marketplaces:
        range_col = {"sheetId": worksheet.id,
                     "dimension": "COLUMNS",
                     "startIndex": col_map[marketplace]['index'],
                     "endIndex": max([val['index'] for name, val in col_map.items() if marketplace in name])}
        all_requests.append({"addDimensionGroup": {"range": range_col}})

        all_requests.append({"updateDimensionProperties": {"range": range_col,
                                                           "properties": {"hiddenByUser": True},
                                                           "fields": "hiddenByUser"}})

    # Задаём цвет данным по магазинам
    all_requests.append({"repeatCell": {"range": {"sheetId": worksheet.id,
                                                  "startRowIndex": 0,
                                                  "endRowIndex": len(data),
                                                  "startColumnIndex": 2,
                                                  "endColumnIndex": col_total_i - 1},
                                        "cell": {"userEnteredFormat": {"backgroundColor": COLOR_MARKET_DATA}},
                                        "fields": "userEnteredFormat.backgroundColor"}})

    # Задаём цвет и границы для строк с категориями
    for idx, value in enumerate(data, 1):
        if len(value) == 1 and idx != 1:
            all_requests.append({"updateBorders": {"range": {"sheetId": worksheet.id,
                                                             "startRowIndex": idx - 1,
                                                             "endRowIndex": idx,
                                                             "endColumnIndex": len(data[1])},
                                                   "top": BORDER_STYLE,
                                                   "bottom": BORDER_STYLE}})

    all_requests.append({
        "addConditionalFormatRule": {"rule": {"ranges": [{"sheetId": worksheet.id,
                                                          "startRowIndex": 2,
                                                          "endRowIndex": len(data),
                                                          "startColumnIndex": col_map["Оборачиваемость"]["index"] - 1,
                                                          "endColumnIndex": col_map["Оборачиваемость"]["index"]}],
                                              "booleanRule": {"condition": {"type": "NUMBER_LESS_THAN_EQ",
                                                                            "values": [{"userEnteredValue": "30"}]},
                                                              "format": {"backgroundColor": COLOR_FORMAT}}},
                                     "index": 0}})

    # Маркируем новую страницу цветом
    all_requests.append({"updateSheetProperties": {"properties": {"sheetId": worksheet.id,
                                                                  "tabColor": TAB_COLOR_NEW_SHEET},
                                                   "fields": "tabColor"}})

    # Задаём цвет ячейкам с артикулами
    for idx, row in enumerate(data):
        color = vendor_colors.get(row[0])
        if color:
            end_col = len(data[1]) if len(row) == 1 else 1
            all_requests.append({"repeatCell": {"range": {"sheetId": worksheet.id,
                                                          "startRowIndex": idx,
                                                          "endRowIndex": idx + 1,
                                                          "startColumnIndex": 0,
                                                          "endColumnIndex": end_col},
                                                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                                                "fields": "userEnteredFormat.backgroundColor"}})

    # Добавляем новые строки для дублей и группируем
    for enum, (key, val) in enumerate(sorted(cat_map.items(), key=lambda x: x[0])):
        all_requests.append({"insertDimension": {"range": {"sheetId": worksheet.id,
                                                           "dimension": "ROWS",
                                                           "startIndex": key + 1 + enum,
                                                           "endIndex": key + 2 + enum},
                                                 "inheritFromBefore": False}})
        range_col = {"sheetId": worksheet.id,
                     "dimension": "ROWS",
                     "startIndex": key + 2 + enum,
                     "endIndex": max(val['index_row']) + 2 + enum}
        all_requests.append({"addDimensionGroup": {"range": range_col}})

        all_requests.append({"updateDimensionProperties": {"range": range_col,
                                                           "properties": {"hiddenByUser": True},
                                                           "fields": "hiddenByUser"}})

    # Отправляем запрос на форматирование
    spreadsheet.batch_update({"requests": all_requests})


def stat_orders_update(db_conn: DbConnection, days: int = 1) -> None:
    # Дата за которую формируется лист
    from_date = date.today() - timedelta(days=days)

    # Получаем данные из БД
    orders = db_conn.get_orders(from_date=from_date)
    vendors_in_database = db_conn.get_vendors()
    all_links = db_conn.get_link_wb_card_product()
    links = {}
    for vendor, list_links in all_links.items():
        if len(list_links) == 1:
            links[vendor] = list_links[0]
        else:
            for url in list_links:
                try:
                    check_url = f"https://card.wb.ru/cards/detail?dest=-1029256&nm={url.split('/')[-2]}"
                    response = requests.get(check_url, timeout=5)

                    if response.status_code == 200:
                        data = response.json()
                        if len(data.get('data', {}).get('products', [])):
                            links[vendor] = url
                            break
                    else:
                        continue
                except requests.exceptions.RequestException as e:
                    continue
            else:
                if not links.get(vendor):
                    links[vendor] = list_links[0]

    # Задаем имена шаблонного листа и создаваемого
    sheet_name = SAMPLE
    worksheet_name = from_date.isoformat()

    # Подключение к гугл таблицам
    spreadsheet = initialize_google_sheet()

    # Список данных для таблицы
    data = [[f'{from_date.isoformat()}']]

    worksheet = spreadsheet.worksheet(sheet_name)

    # Проверяем наличие листа, если уже создан создаём заново, первоначальный лист становится копией
    hide_and_rename_existing_sheet(spreadsheet, worksheet_name)

    # Создаём новый лист
    new_worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=300, cols=45)

    # Сортируем листы для удобства
    reorder_sheets(spreadsheet=spreadsheet)

    keep_first_n_sheets(spreadsheet, n=90)

    # Собираем данные из шаблона
    vendors = worksheet.col_values(1) + ['Остальное']
    comments = worksheet.col_values(2)
    counts = worksheet.col_values(3)
    delivery_dates = worksheet.col_values(4)

    markets = []  # Список магазинов
    marketplaces = ['OZON', 'YANDEX', 'WB']  # Список маркетплейсов
    data_map = {}  # Словарь для данных
    col_map = {}  # Словарь колонок с индексами

    # Сортировка данных из БД
    for order in sorted(orders, key=lambda x: x.vendor_code):
        # Добавление артиклулов отсутствующих в шаблоне
        vendor = order.vendor_code.strip().lower()
        if vendor not in [v.strip().lower() for v in vendors]:
            vendors.append(vendor)

        # Формирование списка магазинов
        market = f"{order.client.marketplace}\n{order.client.name_company.split()[0]}".upper()
        if market not in markets:
            markets.append(market)

        # Формирование словаря данных
        data_map.setdefault(vendor, {})
        data_map[vendor][market] = order.orders_count

    # Сортировка магазинов по маркетплейсу и названию
    markets.sort(key=lambda x: (marketplaces.index(x.split()[0]) if x.split()[0] in marketplaces else float('inf'),
                                x.split()[0], x.split()[-1]))
    marketplaces = []
    other = True

    # Формирование строк данных
    for i, vendor in enumerate(vendors, 2):
        row = [vendor]

        # Строка с заголовками
        if i == 2:
            row.append('Ссылка')
            for market in markets:
                # Формировние списков маркетплейсов
                marketplace = market.split()[0]
                if marketplace not in row:
                    marketplaces.append(marketplace)
                    row.append(marketplace)

                row.append(market)

            # Добавляем обязательные заголовки
            row += ['Итого', 'Оборачиваемость', 'Итого остаток',
                    'Комментарий', 'Кол-во', 'Дата прихода', 'Дней до прихода']

            # Формируем словарь заголовков с цифровыми и буквенными индексами
            for j, val in enumerate(row, 1):
                col_map[val] = {'index': j, 'letter': column_to_letter(j)}

            data.append(row)
            continue

        # Строки с категориями
        if vendor.strip().lower() not in vendors_in_database and other:
            if vendor == 'Остальное':
                other = False
            data.append(row)
            continue

        # Добавляем ссылку на товар
        link = links.get(vendor.lower().strip(), '')
        if link:
            row.append(link)
        else:
            row.append('')

        # Строки с данными
        for market in markets:
            marketplace = market.split()[0]
            # Для каждого маркетплейса добавляем формулу суммы данных по магазинам
            if len(row) + 1 == col_map.get(marketplace, {}).get('index', 0):
                # Получаем буквенные индексы первого и последнего магазина по маркетплейсу
                letters = [val['letter'] for name, val in sorted(col_map.items(), key=lambda x: x[1]['index']) if
                           marketplace in name]
                row.append(f'=СУММ({letters[1]}{i}:{letters[-1]}{i})')
            # Добавляем данные по магазинам
            row.append(data_map.get(vendor.strip().lower(), {}).get(market, 0))

        # Добавляем формулу итоговой суммы данных по всем маркетплейсам
        row.append(
            f'''=СУММ({"; ".join([f"{col_map[marketplace]['letter']}{i}" for marketplace in marketplaces])})''')

        col_total = col_map["Итого"]["letter"]
        col_total_stock_l = col_map["Итого остаток"]["letter"]

        # Добавляем формулу оборачиваемости
        row.append(f'=ЕСЛИ({col_total}{i}=0;0;ОКРУГЛ({col_total_stock_l}{i}/{col_total}{i};0))')

        # Добавляем формулу итоговых остатков
        prev_sheet = (from_date - timedelta(days=1)).isoformat()
        row.append(
            f"""=ЕСЛИОШИБКА(ВПР(A{i};ДВССЫЛ("'{prev_sheet}'!$A$1:$WW$1000");"""
            f"""ПОИСКПОЗ({col_total_stock_l}2;ДВССЫЛ("'{prev_sheet}'!$A$2:$WW$2");0);ЛОЖЬ);0)-{col_total}{i}""")

        # Добавляем данные из шаблона из столбцов Комментарий, Кол-во, Дата прихода
        if len(row) != 1:
            row.append(next(iter(comments[i - 2:i - 1]), ''))
            row.append(next(iter(counts[i - 2:i - 1]), ''))
            row.append(next(iter(delivery_dates[i - 2:i - 1]), ''))
            cell_date = f"ИНДЕКС({column_to_letter(len(row))}:{column_to_letter(len(row))}; СТРОКА())"
            row.append(
                f"""=ЕСЛИ(ИЛИ({cell_date}=""; НЕ(ЕЧИСЛО({cell_date}))); ""; ЕСЛИ({cell_date}<СЕГОДНЯ();"""
                f""""Дата прошла"; РАЗНДАТ(СЕГОДНЯ(); {cell_date}; "D")))""")

        data.append(row)

    # Подсчёт данных по дублям
    cat_map = {}
    default = None

    # Сбор информации по строкам с дублями
    for index, row in enumerate(data[2:], 2):
        if len(row) == 1 and 'дубли' in row[0].lower().split():
            default = index
            cat_map.setdefault(default, {'index_row': [], 'data': []})
        elif len(row) == 1:
            default = None
        else:
            if cat_map.get(default) is not None:
                cat_map[default]['index_row'].append(index)

    # Получение индексов столбцов с итогами
    col_total_i = col_map['Итого']['index'] - 1
    col_total_l = col_map['Итого']['letter']
    col_turnover_l = col_map['Оборачиваемость']['letter']
    col_total_stock_i = col_map["Итого остаток"]["index"] - 1
    col_total_stock_l = col_map["Итого остаток"]["letter"]

    no_duplicates = []
    n = 0

    # Формирование данных по дублям
    for enum, (key, val) in enumerate(cat_map.items(), 1):
        enum -= n
        indexes = val['index_row']
        if len(indexes) > 1:
            new_row = copy(data[min(indexes)])
            for i, v in enumerate(new_row):
                if i < 2 or i > col_total_stock_i:
                    continue
                elif i in [col_map[mp]['index'] - 1 for mp in marketplaces] + [col_total_i, col_total_i + 1]:
                    new_row[i] = v.replace(f'{min(indexes) + 1}', f'{key + 1 + enum}')
                elif i == col_total_stock_i:
                    new_row[i] = v.replace(f'A{min(indexes) + 1}', f'A{key + 1 + enum}').replace(
                        f'{col_total_l}{min(indexes) + 1}', f'{col_total_l}{key + 1 + enum}')
                else:
                    for idx in [i for i in indexes if i != min(indexes)]:
                        new_row[i] += data[idx][i]
            for idx in indexes:
                for pos in range(col_total_stock_i, len(data[idx])):
                    data[idx][pos] = ''
            cat_map[key]['data'] = new_row
        else:
            n += 1
            no_duplicates.append(key)

    for key in no_duplicates:
        cat_map.pop(key)

    # Записываем данные в гугл таблицу
    new_worksheet.update(range_name='A1', values=data, value_input_option=ValueInputOption("USER_ENTERED"))

    # Форматируем лист
    format_sheet(spreadsheet=spreadsheet,
                 worksheet=new_worksheet,
                 data=data,
                 col_map=col_map,
                 cat_map=cat_map,
                 marketplaces=marketplaces)

    # Добавление данных по дублям
    all_updates = []
    for enum, (key, val) in enumerate(sorted(cat_map.items(), key=lambda x: x[0])):
        indexes = val['index_row']
        all_updates.append({"range": f"A{key + 2 + enum}", "values": [val['data']]})
        all_updates.append({"range": f"{col_turnover_l}{min(indexes) + 2 + enum}:"
                                     f"{col_turnover_l}{max(indexes) + 2 + enum}",
                            "values": [[
                                f'=ЕСЛИ({col_total_l}{idx + 2 + enum}=0;0;ОКРУГЛ('
                                f'{col_total_stock_l}{min(indexes) + 1 + enum}/{col_total_l}{idx + 2 + enum};0))']
                                for idx in indexes
                            ]})

    # Выполнение одного обновления для всех изменений
    new_worksheet.batch_update(all_updates, value_input_option=ValueInputOption("USER_ENTERED"))


def _sheets_cell_to_date(value: str):
    """Парсит дату из ячейки Google Sheets: int/float (epoch 1899-12-30) или строка."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        num = float(value)
        return (datetime(1899, 12, 30) + timedelta(days=num)).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _nearest_supply(comment: str, qty_str: str, date_str: str, today: date):
    """Возвращает (qty, delivery_date) ближайшей будущей поставки или (None, None).

    Приоритет — пары '<кол-во> <dd.mm.yyyy>' в комментарии; иначе fallback на колонки
    Кол-во/Дата прихода Шаблона.
    """
    pairs = []
    for q_s, d_s in re.findall(r"(\d+)\s+(\d{2}\.\d{2}\.\d{4})", comment or ''):
        try:
            d = datetime.strptime(d_s, "%d.%m.%Y").date()
            pairs.append((int(q_s), d))
        except ValueError:
            continue
    future = [p for p in pairs if p[1] >= today]
    if future:
        future.sort(key=lambda x: x[1])
        return future[0]

    qty = None
    try:
        qty = int((qty_str or '').strip())
    except ValueError:
        qty = None
    d = _sheets_cell_to_date(date_str)
    if qty is not None and d is not None and d >= today:
        return (qty, d)
    return (None, None)


def _read_to_today_totals(spreadsheet: gspread.Spreadsheet) -> tuple[dict, dict, dict]:
    """Читает лист 'ТО сегодня' и агрегирует per-vendor (ключ — vendor в lower):
       FBO (C+F+I+L), FBS (O+Q), Приёмка (D+G+J+M+P).
    Эти суммы — ровно то, что формулы fbo_formula/fbs_formula/priyomka_formula
    пишут на лист; нужно, чтобы Python-ABC считался на тех же данных, что и
    формулы в ячейках (иначе AB/AC/AD в сheet и Расшифровка могут разойтись)."""
    try:
        ws = spreadsheet.worksheet(TO_TODAY)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Лист '%s' не найден — Python-метрики не будут выравнены "
                       "с формулами FBO/FBS/Приёмки", TO_TODAY)
        return {}, {}, {}

    rows = ws.get('A1:Q', value_render_option='UNFORMATTED_VALUE')

    def _num(row: list, idx: int) -> float:
        if idx >= len(row):
            return 0.0
        v = row[idx]
        if v in ('', None):
            return 0.0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    fbo: dict[str, float] = {}
    fbs: dict[str, float] = {}
    priy: dict[str, float] = {}
    for row in rows:
        if not row or not row[0]:
            continue
        vendor = str(row[0]).strip().lower()
        if not vendor:
            continue
        # FBO = C+F+I+L (индексы 2, 5, 8, 11)
        fbo_add = _num(row, 2) + _num(row, 5) + _num(row, 8) + _num(row, 11)
        # FBS = O+Q (индексы 14, 16)
        fbs_add = _num(row, 14) + _num(row, 16)
        # Приёмка = D+G+J+M+P (индексы 3, 6, 9, 12, 15)
        priy_add = _num(row, 3) + _num(row, 6) + _num(row, 9) + _num(row, 12) + _num(row, 15)
        fbo[vendor] = fbo.get(vendor, 0.0) + fbo_add
        fbs[vendor] = fbs.get(vendor, 0.0) + fbs_add
        priy[vendor] = priy.get(vendor, 0.0) + priy_add
    return fbo, fbs, priy


def clear_row_groups(spreadsheet: gspread.Spreadsheet, sheet_id: int) -> None:
    """Удаляет все группы строк/колонок и правила условного форматирования на листе."""
    creds = Credentials.from_service_account_file(PATH_JSON, scopes=SCOPE)
    service = build('sheets', 'v4', credentials=creds, cache_discovery=False)

    response = service.spreadsheets().get(
        spreadsheetId=spreadsheet.id,
        fields=('sheets(properties(sheetId),rowGroups(depth,range),'
                'columnGroups(depth,range),conditionalFormats)')
    ).execute()

    delete_requests = []
    for sheet in response.get('sheets', []):
        if sheet['properties']['sheetId'] != sheet_id:
            continue
        for group in sheet.get('rowGroups', []):
            r = {"sheetId": sheet_id, "dimension": "ROWS",
                 "startIndex": group['range']['startIndex'],
                 "endIndex": group['range']['endIndex']}
            for _ in range(group.get('depth', 1)):
                delete_requests.append({"deleteDimensionGroup": {"range": r}})
        for group in sheet.get('columnGroups', []):
            r = {"sheetId": sheet_id, "dimension": "COLUMNS",
                 "startIndex": group['range']['startIndex'],
                 "endIndex": group['range']['endIndex']}
            for _ in range(group.get('depth', 1)):
                delete_requests.append({"deleteDimensionGroup": {"range": r}})
        cf_count = len(sheet.get('conditionalFormats', []))
        # Удаляем с конца, чтобы индексы не сдвигались.
        for i in range(cf_count - 1, -1, -1):
            delete_requests.append({"deleteConditionalFormatRule":
                                        {"sheetId": sheet_id, "index": i}})

    if delete_requests:
        spreadsheet.batch_update({"requests": delete_requests})


def format_week_sheet(worksheet: gspread.Worksheet, spreadsheet: gspread.Spreadsheet,
                      headers1: list, headers2: list, dub_ranges: list[tuple[int, int]],
                      totals_row_indices: list[int] | None = None,
                      section_row_indices: list[int] | None = None,
                      market_data_range: tuple[int, int] | None = None,
                      china_data_range: tuple[int, int] | None = None) -> None:
    """Форматирование листа Неделька: мерджи шапки, заморозка, выравнивание, группировки.

    totals_row_indices — список 1-based строк с тоталами (все тоталы, вкл. grand+секции).
        Заливка серым + bold.
    section_row_indices — 1-based строки секционных подзаголовков (Рынок/Китай). Поверх
        серой заливки — пастельно-синий COLOR_SECTION_TOTALS.
    market_data_range / china_data_range — (first_row, last_row) 1-based диапазоны строк
        данных секции. Используются для row-group (раскрывается/сворачивается, по умолчанию
        развернуто)."""
    if totals_row_indices is None:
        totals_row_indices = [3]
    if section_row_indices is None:
        section_row_indices = []
    sheet_id = worksheet.id
    n_cols = len(headers2)

    # Очищаем существующие группы строк перед добавлением новых
    clear_row_groups(spreadsheet, sheet_id)

    all_requests = []

    # Полный сброс форматирования по листу — чтобы при изменениях колонок старые
    # стили (заливка, шрифт, числовые форматы) не оставались висеть от прошлого запуска.
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id},
                                        "cell": {},
                                        "fields": "userEnteredFormat"}})

    # Сбрасываем hiddenByUser на всех строках листа: иначе строки, спрятанные прошлым
    # прогоном (когда группы создавались как свёрнутые), остаются невидимыми и после
    # повторной записи, даже если новый прогон не помечает их как hidden.
    all_requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "ROWS"},
        "properties": {"hiddenByUser": False},
        "fields": "hiddenByUser",
    }})

    # Сбрасываем мерджи шапки на случай повторного запуска
    # endColumnIndex намеренно опущен — диапазон должен покрывать ВСЕ существующие
    # мерджи в шапке (с прошлых запусков, когда ширина листа могла отличаться),
    # иначе unmergeCells падает с "must select all cells in a merged range".
    all_requests.append({"unmergeCells": {"range": {"sheetId": sheet_id,
                                                    "startRowIndex": 0,
                                                    "endRowIndex": 2,
                                                    "startColumnIndex": 0}}})

    # Горизонтальные мерджи в первой строке шапки: непустая ячейка + пустые справа
    i = 0
    while i < n_cols:
        if headers1[i]:
            j = i + 1
            while j < n_cols and not headers1[j]:
                j += 1
            if j - i > 1:
                all_requests.append({"mergeCells": {"range": {"sheetId": sheet_id,
                                                              "startRowIndex": 0,
                                                              "endRowIndex": 1,
                                                              "startColumnIndex": i,
                                                              "endColumnIndex": j},
                                                    "mergeType": "MERGE_ALL"}})
            i = j
        else:
            i += 1

    # Шапка: жирный белый текст, центр, тёмно-синяя заливка, перенос
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 0,
                                                  "endRowIndex": 2,
                                                  "startColumnIndex": 0,
                                                  "endColumnIndex": n_cols},
                                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER",
                                                                       "verticalAlignment": "MIDDLE",
                                                                       "wrapStrategy": "WRAP",
                                                                       "backgroundColor": COLOR_HEADER,
                                                                       "textFormat": {"bold": True,
                                                                                      "foregroundColor": COLOR_HEADER_TEXT}}},
                                        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,"
                                                  "wrapStrategy,backgroundColor,textFormat)"}})

    # Белые границы со всех сторон у двух строк шапки
    white_border = {"style": "SOLID", "width": 1,
                    "color": {"red": 1, "green": 1, "blue": 1}}
    all_requests.append({"updateBorders": {"range": {"sheetId": sheet_id,
                                                     "startRowIndex": 0,
                                                     "endRowIndex": 2,
                                                     "startColumnIndex": 0,
                                                     "endColumnIndex": n_cols},
                                           "top": white_border,
                                           "bottom": white_border,
                                           "left": white_border,
                                           "right": white_border,
                                           "innerHorizontal": white_border,
                                           "innerVertical": white_border}})

    # Закрепляем первые 3 строки (2 шапки + "ВСЕГО (мейны)") и 2 колонки.
    # Строки "ВСЕГО (Рынок)" / "ВСЕГО (Китай)" — секционные подзаголовки внутри данных,
    # не закрепляются (участвуют в обычной фильтрации).
    all_requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": 3, "frozenColumnCount": 2}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
    }})

    # Для каждой тоталовой строки — серый фон + bold.
    for r_num in totals_row_indices:
        r0 = r_num - 1  # 1-based → 0-based
        all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                      "startRowIndex": r0,
                                                      "endRowIndex": r0 + 1,
                                                      "startColumnIndex": 0,
                                                      "endColumnIndex": n_cols},
                                            "cell": {"userEnteredFormat": {
                                                "backgroundColor": COLOR_MAIN_ROW,
                                                "textFormat": {"bold": True}}},
                                            "fields": "userEnteredFormat(backgroundColor,textFormat.bold)"}})

    # Секционные подзаголовки (Рынок/Китай) — поверх серого окрашиваем в
    # пастельно-синий COLOR_SECTION_TOTALS, чтобы визуально отличить от grand totals.
    for r_num in section_row_indices:
        r0 = r_num - 1
        all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                      "startRowIndex": r0,
                                                      "endRowIndex": r0 + 1,
                                                      "startColumnIndex": 0,
                                                      "endColumnIndex": n_cols},
                                            "cell": {"userEnteredFormat": {
                                                "backgroundColor": COLOR_SECTION_TOTALS}},
                                            "fields": "userEnteredFormat.backgroundColor"}})

    # Чёрная нижняя граница 2px под закреплённой строкой 3 — визуальный разделитель
    # границы закрепа. У секционных подзаголовков своих границ не рисуем (блочные
    # границы вокруг каждого мейна+дубли и так подчеркнут структуру).
    black_border_med = {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}}
    all_requests.append({"updateBorders": {"range": {"sheetId": sheet_id,
                                                     "startRowIndex": 2,
                                                     "endRowIndex": 3,
                                                     "startColumnIndex": 0,
                                                     "endColumnIndex": n_cols},
                                           "bottom": black_border_med}})

    # Границы секционных подзаголовков вешаем ПОЗЖЕ (в group_requests, после блочных
    # 2px границ), иначе они перебьют нашу рамку. См. комментарий ниже.

    # Ширина колонок (34 столбца, добавлена "Стоимость стока" на позиции R):
    #   A=100 (Магазин), B=190 (Артикул),
    #   C-J=60 (Стоки: FBO, FBS, Приёмка, Итого / Заказы / Оборачиваемость),
    #   K-O=70 (Маржа + ROI + три GMROI),
    #   P-AA=80 (Выручка, Себес, Стоимость стока, 7 компонентов + Сток на начало + Кол-во продаж),
    #   AB-AD=70 (три ABC), AE=400 (Расшифровка), AF-AG=60 (Ближайшая поставка),
    #   AH=120 (Комментарий).
    column_widths = [(0, 1, 100), (1, 2, 190), (2, 10, 60),
                     (10, 15, 70), (15, 27, 80), (27, 30, 70),
                     (30, 31, 400), (31, 33, 60), (33, 34, 120)]
    for start_col, end_col, width in column_widths:
        all_requests.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id,
                                                                     "dimension": "COLUMNS",
                                                                     "startIndex": start_col,
                                                                     "endIndex": end_col},
                                                           "properties": {"pixelSize": width},
                                                           "fields": "pixelSize"}})

    # Выравнивание по центру всех колонок кроме первых двух (C..AH, включая Расшифровку
    # и Комментарий).
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 2,
                                                  "endColumnIndex": 34},
                                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat.horizontalAlignment"}})

    # Перенос текста для Расшифровки (AE=30) — там длинная подсказка по ABC.
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 30,
                                                  "endColumnIndex": 31},
                                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                                        "fields": "userEnteredFormat.wrapStrategy"}})

    # Вертикальное выравнивание по центру для всех ячеек листа
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id},
                                        "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE"}},
                                        "fields": "userEnteredFormat.verticalAlignment"}})

    # Условное форматирование трёх колонок ABC (AB..AD, индексы 27..30):
    # A=зелёный, B=жёлтый, C=красный. С 3-й строки — у тоталовых и секционных строк
    # ячейки ABC пустые, правило TEXT_EQ("A"/"B"/"C") не сработает → без заливки.
    for value, color in (('A', COLOR_ABC_A), ('B', COLOR_ABC_B), ('C', COLOR_ABC_C)):
        all_requests.append({"addConditionalFormatRule": {
            "rule": {"ranges": [{"sheetId": sheet_id,
                                 "startRowIndex": 2,
                                 "startColumnIndex": 27,
                                 "endColumnIndex": 30}],
                     "booleanRule": {"condition": {"type": "TEXT_EQ",
                                                   "values": [{"userEnteredValue": value}]},
                                     "format": {"backgroundColor": color}}},
            "index": 0,
        }})

    # Заливка строк главных артикулов серым
    for first_dub, _ in dub_ranges:
        agg_row_0 = first_dub - 2
        all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                      "startRowIndex": agg_row_0,
                                                      "endRowIndex": agg_row_0 + 1,
                                                      "startColumnIndex": 0,
                                                      "endColumnIndex": n_cols},
                                            "cell": {"userEnteredFormat": {"backgroundColor": COLOR_MAIN_ROW}},
                                            "fields": "userEnteredFormat.backgroundColor"}})

    # Числовой формат #,##0 для C..J (Стоки: FBO, FBS, Приёмка, Итого / Заказы / Оборач.)
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 2,
                                                  "endColumnIndex": 10},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER",
                                                                                        "pattern": "#,##0"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})

    # Процентный формат для Маржа + ROI + три GMROI (K..O) с разделителем тысяч
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 10,
                                                  "endColumnIndex": 15},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT",
                                                                                        "pattern": "#,##0.00%"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})

    # Числовой формат #,##0 для P..AA (Выручка, Себес, Стоимость стока, 7 компонентов
    # + Сток на начало + Кол-во продаж).
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 15,
                                                  "endColumnIndex": 27},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER",
                                                                                        "pattern": "#,##0"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})

    # Числовой формат #,##0 для AF..AG (Ближайшая поставка: Дней до / Кол-во).
    # AE (30) — Расшифровка, текст, в этот диапазон не входит.
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 31,
                                                  "endColumnIndex": 33},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER",
                                                                                        "pattern": "#,##0"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})

    # Шрифт Calibri на весь лист (только fontFamily, не затирает bold шапки)
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id},
                                        "cell": {"userEnteredFormat": {"textFormat": {"fontFamily": "Calibri"}}},
                                        "fields": "userEnteredFormat.textFormat.fontFamily"}})

    # Чёрная рамка 2px вокруг каждого блока (агрегат + дубли).
    black_border = {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}}
    for first_dub, last_dub in dub_ranges:
        all_requests.append({"updateBorders": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": first_dub - 2,
                      "endRowIndex": last_dub,
                      "startColumnIndex": 0,
                      "endColumnIndex": n_cols},
            "top": black_border,
            "bottom": black_border,
            "left": black_border,
            "right": black_border,
        }})

    # Группируем GMROI неделя + GMROI месяц (N..O, 13..15) и сворачиваем по умолчанию
    range_gmroi = {"sheetId": sheet_id,
                   "dimension": "COLUMNS",
                   "startIndex": 13,
                   "endIndex": 15}
    all_requests.append({"addDimensionGroup": {"range": range_gmroi}})
    all_requests.append({"updateDimensionProperties": {"range": range_gmroi,
                                                       "properties": {"hiddenByUser": True},
                                                       "fields": "hiddenByUser"}})

    # Группируем компоненты + Стоимость стока + Сток на начало + Кол-во продаж
    # (P..AA, 15..27) и сворачиваем.
    range_cols = {"sheetId": sheet_id,
                  "dimension": "COLUMNS",
                  "startIndex": 15,
                  "endIndex": 27}
    all_requests.append({"addDimensionGroup": {"range": range_cols}})
    all_requests.append({"updateDimensionProperties": {"range": range_cols,
                                                       "properties": {"hiddenByUser": True},
                                                       "fields": "hiddenByUser"}})

    # Группируем Расшифровку (AE, 30..31) и сворачиваем — широкая колонка с подсказкой,
    # удобно скрывать по умолчанию.
    range_desc = {"sheetId": sheet_id,
                  "dimension": "COLUMNS",
                  "startIndex": 30,
                  "endIndex": 31}
    all_requests.append({"addDimensionGroup": {"range": range_desc}})
    all_requests.append({"updateDimensionProperties": {"range": range_desc,
                                                       "properties": {"hiddenByUser": True},
                                                       "fields": "hiddenByUser"}})

    # Применяем основной batch (без row-groups и без изменения rowCount).
    spreadsheet.batch_update({"requests": all_requests})

    if dub_ranges:
        last_data_row = dub_ranges[-1][1]

        # Сначала — расширяем grid до last_data_row + 10 (добавляем 10 пустых строк
        # после данных). Отдельным batch'ем, чтобы Sheets зафиксировал новый rowCount.
        spreadsheet.batch_update({"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": sheet_id,
                           "gridProperties": {"rowCount": last_data_row + 10}},
            "fields": "gridProperties.rowCount",
        }}]})

        # Затем — верхняя граница 2px на первой пустой строке после данных
        # (закрывает таблицу снизу). Grid уже расширен — границу есть куда нарисовать.
        group_requests = [{"updateBorders": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": last_data_row,
                      "endRowIndex": last_data_row + 1,
                      "startColumnIndex": 0,
                      "endColumnIndex": n_cols},
            "top": black_border,
        }}]

        # Тонкие вертикальные разделители 1px (строки 3..last_data_row) на границах
        # логических групп колонок:
        #   right Артикул (B=1), right Итого стоков (F=5),
        #   right Неделя заказов (H=7), right Неделя оборач. (J=9),
        #   right GMROI год (M=12), right ABC оборач. (AD=29),
        #   left Дней до (AF=31) — отделяет Ближайшую поставку.
        thin_black = {"style": "SOLID", "width": 1,
                      "color": {"red": 0, "green": 0, "blue": 0}}
        vertical_lines = [(1, 'right'), (5, 'right'), (7, 'right'),
                          (9, 'right'), (12, 'right'), (29, 'right'),
                          (31, 'left')]
        for col_idx, side in vertical_lines:
            group_requests.append({"updateBorders": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": 2,
                          "endRowIndex": last_data_row,
                          "startColumnIndex": col_idx,
                          "endColumnIndex": col_idx + 1},
                side: thin_black,
            }})
        # Row-groups для секций Рынок и Китай. Группа покрывает только строки ДАННЫХ
        # (без секционного подзаголовка), чтобы при сворачивании подзаголовок оставался
        # виден. По умолчанию группа развёрнута — hiddenByUser не ставим.
        for section_range in (market_data_range, china_data_range):
            if section_range is None:
                continue
            first_r, last_r = section_range
            group_requests.append({"addDimensionGroup": {"range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": first_r - 1,
                "endIndex": last_r,
            }}})

        # Полная 2px чёрная рамка вокруг каждого секционного подзаголовка. Делаем
        # здесь (а не в основном batch), чтобы наши границы не были перекрыты 2px
        # границами блоков дублей, которые идут выше по порядку запросов.
        for r_num in section_row_indices:
            r0 = r_num - 1
            group_requests.append({"updateBorders": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": r0,
                          "endRowIndex": r0 + 1,
                          "startColumnIndex": 0,
                          "endColumnIndex": n_cols},
                "top": black_border,
                "bottom": black_border,
                "left": black_border,
                "right": black_border,
            }})

        # Создаём row-groups для дублей (вложенные в секционные). Свёрнуты по умолчанию.
        for first_dub, last_dub in dub_ranges:
            r_rows = {"sheetId": sheet_id,
                      "dimension": "ROWS",
                      "startIndex": first_dub - 1,
                      "endIndex": last_dub}
            group_requests.append({"addDimensionGroup": {"range": r_rows}})
            group_requests.append({"updateDimensionProperties": {"range": r_rows,
                                                                  "properties": {"hiddenByUser": True},
                                                                  "fields": "hiddenByUser"}})
        spreadsheet.batch_update({"requests": group_requests})


def update_week_sheet(db_conn: DbConnection):
    logger.info('=== update_week_sheet: старт ===')
    spreadsheet = initialize_google_sheet()

    worksheet_week = spreadsheet.worksheet(WEEK)
    worksheet_sample = spreadsheet.worksheet(SAMPLE)
    logger.info('Открыт spreadsheet "%s", листы %s/%s готовы', PROJECT, SAMPLE, WEEK)

    # Стоки — 4 подколонки (FBO, FBS, Приёмка, Итого). Показатели — 21 подколонка
    # (добавили "Стоимость стока" между Себесом и Комиссией — helper для честного GMROI
    # на уровне портфеля). Итого 34 колонки.
    headers1 = ["", "", "Стоки", "", "", "", "Заказы", "", "Оборачиваемость", "",
                "Показатели", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
                "Ближайшая поставка", "",
                ""]
    headers2 = [
        "Магазин", "Артикул", "FBO", "FBS", "Приёмка", "Итого", "Вчера", "Неделя",
        "Вчера", "Неделя",
        "Маржа", "ROI",
        "GMROI год", "GMROI неделя", "GMROI месяц",
        "Выручка", "Себес", "Стоимость стока",
        "Комиссия", "Эквайринг",
        "Логистика", "Хранение", "Реклама", "Прочее", "Налог",
        "Сток на начало", "Кол-во продаж",
        "ABC выручка", "ABC ROI", "ABC оборач.", "Расшифровка",
        "Дней до", "Кол-во",
        "Комментарий",
    ]

    # vendors_map_ci — case-insensitive: ключ и main_vendor приведены к нижнему регистру.
    # В шаблоне артикулы могут быть в любом регистре (например "5002/5Лопрыск"), а в БД
    # они нормализованы в lower — сравниваем без учёта регистра.
    logger.info('[1/7] Загружаю vendors_map из БД...')
    vendors_map_raw = db_conn.get_vendors_map()
    # vendors_map: vendor_lower → (main_lower, type, marker). marker='market' → Рынок,
    # пусто → Китай.
    vendors_map: dict[str, tuple[str, str, str]] = {
        k.lower(): ((v[0] or '').lower(), v[1], (v[2] or '').strip().lower())
        for k, v in vendors_map_raw.items()
    }
    _mains_market = sum(1 for _, (_mv, _t, _mk) in vendors_map.items()
                        if _t == 'main' and _mk == 'market')
    _mains_china = sum(1 for _, (_mv, _t, _mk) in vendors_map.items()
                       if _t == 'main' and _mk != 'market')
    logger.info('vendors_map: %d артикулов (main=%d: рынок=%d/китай=%d, maindouble=%d)',
                len(vendors_map),
                sum(1 for _, (_mv, _t, _mk) in vendors_map.items() if _t == 'main'),
                _mains_market, _mains_china,
                sum(1 for _, (_mv, _t, _mk) in vendors_map.items() if _t == 'maindouble'))

    # Читаем колонки шаблона A..D одним запросом: A=Артикул, B=Комментарий, C=Кол-во, D=Дата прихода
    logger.info('[2/7] Читаю шаблон (A:D)...')
    template_rows = worksheet_sample.get('A:D')
    template_info: dict[str, tuple[str, str, str]] = {}
    template_vendors: list[str] = []
    seen: set[str] = set()
    for row in template_rows:
        a_raw = (row[0] if len(row) > 0 else '').strip()
        if not a_raw:
            continue
        a = a_raw.lower()  # все ключи нормализованы — case-insensitive сопоставление
        # Табы в комментарии при USER_ENTERED расцениваются как разделитель ячеек —
        # заменяем на пробелы, чтобы текст не разрывался по столбцам.
        b = (row[1] if len(row) > 1 else '').replace('\t', ' ')
        c = row[2] if len(row) > 2 else ''
        d = row[3] if len(row) > 3 else ''
        # Если комментарий пуст, но в Кол-во (C) и Дате прихода (D) что-то есть —
        # собираем комментарий из них в формате "<кол-во>    <dd.mm.yyyy>" (4 пробела).
        if not b.strip() and c.strip() and d.strip():
            d_parsed = _sheets_cell_to_date(d)
            d_text = d_parsed.strftime("%d.%m.%Y") if d_parsed else d.strip()
            b = f"{c.strip()}    {d_text}"
        template_info.setdefault(a, (b, c, d))
        if a in vendors_map and a not in seen:
            template_vendors.append(a)
            seen.add(a)
    logger.info('Из шаблона взято %d уникальных артикулов (найдены в vendors_map); '
                'строк в template_info: %d', len(template_vendors), len(template_info))

    # Инвертированный индекс по всей БД: main_vendor → [все артикулы блока, включая
    # сам main]. Нужен, чтобы для каждого артикула из шаблона подтянуть ПОЛНЫЙ блок
    # (все дубли того же main), даже если самих этих дублей в шаблоне нет.
    main_to_all: dict[str, list[str]] = {}
    for v, (mv, _tp, _mk) in vendors_map.items():
        main_to_all.setdefault(mv, []).append(v)
    # Внутри каждого блока сортируем дубли по алфавиту для стабильности (main
    # ставится отдельно первой строкой ниже).
    for mv in main_to_all:
        main_to_all[mv].sort()

    # Маркер мейна (из записи самого main в справочнике). Если самого main в справочнике
    # нет (аномалия) — берём маркер первого попавшегося дубля этой группы.
    main_marker: dict[str, str] = {}
    for v, (mv, _tp, _mk) in vendors_map.items():
        if _tp == 'main':
            main_marker[v] = _mk
    for mv, members in main_to_all.items():
        if mv not in main_marker:
            for m in members:
                _mk = vendors_map.get(m, ('', '', ''))[2]
                if _mk:
                    main_marker[mv] = _mk
                    break
            main_marker.setdefault(mv, '')

    # Группируем: для каждого артикула из шаблона определяем его main и берём ВЕСЬ
    # связанный блок из main_to_all. Один main → один блок (повторные упоминания
    # дублей того же main в шаблоне не плодят повторные блоки).
    blocks: dict[str, list[str]] = {}
    for vendor in template_vendors:
        main_vendor, _type, _marker = vendors_map[vendor]
        if main_vendor in blocks:
            continue
        group = main_to_all.get(main_vendor, [vendor])
        # Main — всегда первым; остальные — после.
        blocks[main_vendor] = [main_vendor] + [v for v in group if v != main_vendor]
    _total_in_blocks = sum(len(v) for v in blocks.values())
    _blocks_market = sum(1 for mv in blocks if main_marker.get(mv) == 'market')
    _blocks_china = len(blocks) - _blocks_market
    logger.info('[3/7] Сформировано %d блоков (рынок=%d, китай=%d), всего артикулов: %d',
                len(blocks), _blocks_market, _blocks_china, _total_in_blocks)

    # Полная группа артикулов по каждому мейну (из vendors_map), включая варианты,
    # которых нет в шаблоне. FBS — общий пул на группу: в БД он может лежать под
    # артикулом мейна или любого варианта. Если мейна нет в шаблоне, в related его
    # тоже нет, и FBS под мейном терялся — поэтому FBS суммируем по всей группе.
    main_to_members: dict[str, set[str]] = {}
    for _v, (_mv, _tv, _mk2) in vendors_map.items():
        if _tv == 'main':
            main_to_members.setdefault(_v, set()).add(_v)
        elif _tv == 'maindouble':
            main_to_members.setdefault(_mv, set()).add(_v)

    def fbs_members(main_vendor: str, related: list) -> set[str]:
        """Все артикулы группы для суммирования FBS-пула (с подстраховкой related+мейн)."""
        return main_to_members.get(main_vendor, set()) | set(related) | {main_vendor}

    # Стоки на день выполнения скрипта
    today = date.today()

    def supply_for(vendor: str) -> tuple:
        """Возвращает (comment, qty, days_until) для строки артикула из данных шаблона."""
        info = template_info.get(vendor)
        if not info:
            return ('', '', '')
        comment, qty_str, date_str = info
        qty, delivery_date = _nearest_supply(comment, qty_str, date_str, today)
        if delivery_date is None:
            return (comment, '', '')
        return (comment, qty, (delivery_date - today).days)

    # Во всех картах ключи vendor_code нормализуем в нижний регистр — иначе
    # данные из БД (которые могут отличаться регистром от шаблона) не будут находиться.
    logger.info('[4/7] Загружаю стоки на сегодня (%s)...', today.isoformat())
    stocks = db_conn.get_stocks_detail(from_date=today)
    stock_map: dict[tuple[str, str], int] = {}
    for s in stocks:
        key = (s.client, (s.vendor_code or '').lower())
        stock_map[key] = stock_map.get(key, 0) + s.quantity
    logger.info('    стоки сегодня: %d записей, %d ключей (client, vendor)',
                len(stocks), len(stock_map))

    # Сток на начало периода (фактический снимок неделю назад).
    _week_ago = today - timedelta(days=7)
    logger.info('    загружаю стоки на начало недели (%s)...', _week_ago.isoformat())
    stocks_start = db_conn.get_stocks_detail(from_date=_week_ago)
    stock_start_map: dict[tuple[str, str], int] = {}
    for s in stocks_start:
        key = (s.client, (s.vendor_code or '').lower())
        stock_start_map[key] = stock_start_map.get(key, 0) + s.quantity
    logger.info('    стоки на начало: %d записей, %d ключей',
                len(stocks_start), len(stock_start_map))

    # Заказы: вчера и за последние 7 дней (по день, кончая вчерашним)
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=7)
    logger.info('[5/7] Загружаю заказы: вчера (%s) и неделя (%s..%s)...',
                yesterday.isoformat(), week_start.isoformat(), yesterday.isoformat())
    yesterday_orders = db_conn.get_orders(from_date=yesterday)
    week_orders = db_conn.get_orders(from_date=week_start, to_date=yesterday)
    logger.info('    заказов: вчера=%d, за неделю=%d',
                len(yesterday_orders), len(week_orders))

    yesterday_map: dict[tuple[str, str], int] = {}
    for o in yesterday_orders:
        key = (o.client.client_id, (o.vendor_code or '').lower())
        yesterday_map[key] = yesterday_map.get(key, 0) + int(o.orders_count or 0)

    week_map: dict[tuple[str, str], int] = {}
    for o in week_orders:
        key = (o.client.client_id, (o.vendor_code or '').lower())
        week_map[key] = week_map.get(key, 0) + int(o.orders_count or 0)

    # Множество магазинов (client_id), где встречается каждый артикул — из FBO-стоков
    # и из заказов. Один артикул может жить на нескольких магазинах одновременно.
    vendor_clients: dict[str, set[str]] = {}
    for s in stocks:
        if s.client != 'FBS':
            vendor_clients.setdefault((s.vendor_code or '').lower(), set()).add(s.client)
    for o in yesterday_orders + week_orders:
        vendor_clients.setdefault((o.vendor_code or '').lower(), set()).add(o.client.client_id)

    # Справочник по историческим данным -> нужны ВСЕ кабинеты, включая выключенные (is_active=false).
    clients = {c.client_id: c for c in db_conn.get_clients(only_active=False)}

    # Прибыль за неделю с разбивкой: (client_id, vendor_lower) -> dict со всеми статьями
    PROFIT_FIELDS = ('sale', 'cost', 'commission', 'acquiring',
                     'logistics', 'storage', 'advertising', 'other', 'tac',
                     'quantities', 'profit')
    logger.info('[6/7] Загружаю profit за %s..%s (это тяжёлый запрос, ~0.5-60с)...',
                week_start.isoformat(), yesterday.isoformat())
    profit_records = db_conn.get_profit(from_date=week_start, to_date=yesterday)
    logger.info('    получено %d записей прибыли', len(profit_records))
    profit_map: dict[tuple[str, str], dict[str, float]] = {}
    for p in profit_records:
        key = (p.client_id, p.vendor_code)
        s = profit_map.setdefault(key, {k: 0.0 for k in PROFIT_FIELDS})
        s['sale'] += p.sale
        s['cost'] += p.cost
        s['commission'] += p.commission
        s['acquiring'] += p.acquiring
        s['logistics'] += p.logistics
        s['storage'] += p.storage
        s['advertising'] += p.advertising
        s['other'] += p.other
        s['tac'] += p.tac
        s['quantities'] += p.quantities
        s['profit'] += p.profit

    # Сортировка блоков по ABC выручки (Парето 80/95) — для удобства просмотра.
    # Логика точно повторяет SUMPRODUCT-формулу в ячейке:
    #   cum   = сумма значений, где val >= current_val (включая равные и отрицательные)
    #   total = сумма ВСЕХ значений (с отрицательными тоже)
    #   ratio = cum / total → ≤0.8 A, ≤0.95 B, иначе C
    def _classify_pareto(items: list) -> dict:
        result: dict = {}
        total = sum(v for _, v in items)
        if total == 0:
            # все нули / суммы равны — нет смысла классифицировать
            for k, _ in items:
                result[k] = 'C'
            return result
        for key, val in items:
            cum = sum(v for _, v in items if v >= val)
            ratio = cum / total
            result[key] = 'A' if ratio <= 0.80 else ('B' if ratio <= 0.95 else 'C')
        return result

    # Хелперы для сборки дублей — нужны и для пре-паса (ниже), и для главного цикла.
    def components_for_vendor(vendor: str, client_id: str) -> dict | None:
        return profit_map.get((client_id, vendor.lower()))

    def stock_start_for_dub(vendor: str, client_id: str) -> int:
        """Сток FBO на начало периода для дубля (без FBS-пула)."""
        if not client_id:
            return 0
        return stock_start_map.get((client_id, vendor), 0)

    def _compute_dub_rows_data(related: list[str]) -> list[dict]:
        """Собираем список дублей (vendor, client_id) с данными. Отфильтровываем пустые."""
        out: list[dict] = []
        for vendor in related:
            comment_v, qty_v, days_v = supply_for(vendor)
            cids = sorted(vendor_clients.get(vendor, set())) or ['']
            for client_id in cids:
                client = clients.get(client_id) if client_id else None
                mp = client.marketplace if client else ''
                shop = client.name_company.split()[0] if client and client.name_company else ''
                fbo_qty = stock_map.get((client_id, vendor), 0) if client_id else 0
                yest_qty = yesterday_map.get((client_id, vendor), 0) if client_id else 0
                week_qty = week_map.get((client_id, vendor), 0) if client_id else 0
                is_empty = (fbo_qty == 0 and yest_qty == 0 and week_qty == 0
                            and not qty_v and not (comment_v or '').strip())
                if is_empty:
                    continue
                out.append({
                    'vendor': vendor, 'client_id': client_id, 'mp': mp, 'shop': shop,
                    'fbo_qty': fbo_qty, 'yest_qty': yest_qty, 'week_qty': week_qty,
                    'days_v': days_v, 'qty_v': qty_v, 'comment_v': comment_v,
                    'comps': components_for_vendor(vendor, client_id),
                    'stock_start': stock_start_for_dub(vendor, client_id),
                })
        return out

    # Пре-пас: собираем dub_rows_data для каждого блока. Пустые — выбрасываем.
    prebuilt: list[tuple[str, list[str], list[dict]]] = []
    for main_vendor, related in blocks.items():
        dubs = _compute_dub_rows_data(related)
        if dubs:
            prebuilt.append((main_vendor, related, dubs))

    # Читаем 'ТО сегодня' один раз — это тот же источник, что идёт в формулы FBO/FBS/
    # Приёмка на листе. Без этого Python-метрики (block_stock_now) считались бы по БД
    # и расходились с F = Итого в формулах → ABC-оборачиваемость могла бы отличаться.
    logger.info("    читаю лист '%s' для синхронизации Python-ABC с формулами...", TO_TODAY)
    to_today_fbo, to_today_fbs, to_today_priy = _read_to_today_totals(spreadsheet)

    # Метрики блока вычисляем из prebuilt (тот же фильтр is_empty, что видит лист,
    # т.е. считаем только по дублям, которые реально попадут в sheet) и из 'ТО сегодня'
    # (тот же источник стока, что в F=Итого).
    block_revenue: dict[str, float] = {}
    block_profit: dict[str, float] = {}
    block_cost: dict[str, float] = {}
    block_stock_now: dict[str, int] = {}
    block_week_orders: dict[str, int] = {}
    for main_vendor, _related, dubs in prebuilt:
        rev = prof = cost = 0.0
        orders = 0
        for d in dubs:
            c = d['comps']
            if c:
                rev += c['sale']
                prof += c['profit']
                cost += c['cost']
            orders += d['week_qty']
        block_revenue[main_vendor] = rev
        block_profit[main_vendor] = prof
        block_cost[main_vendor] = cost
        block_week_orders[main_vendor] = orders
        # Итого = FBO + FBS + Приёмка (ровно то, что считается в F на листе).
        block_stock_now[main_vendor] = int(to_today_fbo.get(main_vendor, 0)
                                           + to_today_fbs.get(main_vendor, 0)
                                           + to_today_priy.get(main_vendor, 0))

    # Классификация только по тем блокам, что реально показываются (есть в prebuilt).
    prebuilt_mains = [t[0] for t in prebuilt]
    block_rev_classes = _classify_pareto([(mv, block_revenue[mv]) for mv in prebuilt_mains])

    # ROI блока = profit / cost. Парето 80/15/5 — как у выручки.
    block_roi = {mv: (block_profit[mv] / block_cost[mv] if block_cost[mv] > 0 else 0)
                 for mv in prebuilt_mains}
    block_roi_classes = _classify_pareto([(mv, block_roi[mv]) for mv in prebuilt_mains])

    def _block_turnover_class(mv: str) -> str:
        """Класс оборачиваемости блока для Python-сортировки. Пороги зависят от маркера
        мейна: Рынок — 10/15 (строго), Китай — 30/45 (мягко)."""
        orders = block_week_orders.get(mv, 0)
        if orders <= 0:
            return 'C'  # нет заказов — оборачиваемость не считается, кладём в C
        stock = block_stock_now.get(mv, 0)
        days = round(stock * 7 / orders)
        is_market = main_marker.get(mv) == 'market'
        hi_c, hi_b = (15, 10) if is_market else (45, 30)
        return 'C' if days > hi_c else ('B' if days > hi_b else 'A')

    abc_order = {'A': 0, 'B': 1, 'C': 2}

    def _abc_sort_key(mv: str):
        return (abc_order.get(block_rev_classes.get(mv, ''), 3),
                abc_order.get(block_roi_classes.get(mv, ''), 3),
                abc_order.get(_block_turnover_class(mv), 3),
                -block_revenue.get(mv, 0.0))

    # Разделяем prebuilt на Рынок и Китай по маркеру мейна. Сортируем каждую группу
    # отдельно по ABC. На листе Рынок пойдёт перед Китаем.
    prebuilt_by_mv = {t[0]: t for t in prebuilt}
    market_mains = sorted(
        [mv for mv in prebuilt_mains if main_marker.get(mv) == 'market'],
        key=_abc_sort_key,
    )
    china_mains = sorted(
        [mv for mv in prebuilt_mains if main_marker.get(mv) != 'market'],
        key=_abc_sort_key,
    )
    market_data = [prebuilt_by_mv[mv] for mv in market_mains]
    china_data = [prebuilt_by_mv[mv] for mv in china_mains]

    # Диапазон для SUMPRODUCT в ABC-формулах: рассчитаем как 2 шапки + достаточный запас.
    # Точный нижний индекс мы узнаем только после сборки data, поэтому фиксируем верхнюю
    # границу в 10000 — это безопасно для типичных объёмов и допустимо в Sheets.
    ABC_RANGE_END = 10000

    def priyomka_formula(row_idx: int) -> str:
        """Приёмка мейн-артикула — суммируем 5 колонок 'ТО сегодня' (D+G+J+M+P) по вендору из B."""
        r = row_idx
        parts = [f"СУММЕСЛИ('ТО сегодня'!A:A;B{r};'ТО сегодня'!{col}:{col})"
                 for col in ('D', 'G', 'J', 'M', 'P')]
        return '=' + '+'.join(parts)

    def fbo_formula(row_idx: int) -> str:
        """FBO мейн-артикула — суммируем 4 колонки 'ТО сегодня' (C+F+I+L) по вендору из B."""
        r = row_idx
        parts = [f"СУММЕСЛИ('ТО сегодня'!A:A;B{r};'ТО сегодня'!{col}:{col})"
                 for col in ('C', 'F', 'I', 'L')]
        return '=' + '+'.join(parts)

    def fbs_formula(row_idx: int) -> str:
        """FBS мейн-артикула — суммируем 2 колонки 'ТО сегодня' (O+Q) по вендору из B."""
        r = row_idx
        parts = [f"СУММЕСЛИ('ТО сегодня'!A:A;B{r};'ТО сегодня'!{col}:{col})"
                 for col in ('O', 'Q')]
        return '=' + '+'.join(parts)

    def stock_start_main_formula(row_idx: int) -> str:
        """Сток на начало для мейн-артикула — берём столбец R из листа 'ТО -7'
        (снимок остатков неделю назад) по вендору из B. Отрицательные суммы
        (например, техническая коррекция) обрезаем до 0."""
        r = row_idx
        return f"=МАКС(0;СУММЕСЛИ('ТО -7'!A:A;B{r};'ТО -7'!R:R))"

    def stock_value_formula(row_idx: int) -> str:
        """Стоимость стока (R) = (Итого+Сток на начало)/2 × Себес/Кол-во продаж.
        F=Итого, Z=Сток на начало, Q=Себес, AA=Кол-во продаж. При отсутствии продаж
        (AA=0) или ошибке возвращает 0."""
        r = row_idx
        return f'=ЕСЛИОШИБКА((F{r}+Z{r})/2*(Q{r}/AA{r});0)'

    def margin_formula(row_idx: int) -> str:
        """Маржа в колонке K = profit / Выручка. Выручка в P; расходы: Q, S..Y
        (R — helper 'Стоимость стока', не расход, пропускаем)."""
        r = row_idx
        profit = f'(P{r}-Q{r}-S{r}-T{r}-U{r}-V{r}-W{r}-X{r}-Y{r})'
        return f'=ЕСЛИОШИБКА({profit}/P{r};"")'

    def roi_formula(row_idx: int) -> str:
        """ROI в колонке L = profit / Себес. Расходы Q, S..Y; Себес в Q."""
        r = row_idx
        profit = f'(P{r}-Q{r}-S{r}-T{r}-U{r}-V{r}-W{r}-X{r}-Y{r})'
        return f'=ЕСЛИОШИБКА({profit}/Q{r};"")'

    def abc_revenue_formula(row_idx: int) -> str:
        """ABC по выручке (Парето 80/15/5). Главные и дубли — отдельно (A пуст у главных,
        там нет Магазина; у дублей в A стоит "WB Voyor" и т.п.). Выручка в колонке P.
        Диапазон начинается с 5-й строки. Секционные строки "ВСЕГО (…)" (B начинается
        с 'ВСЕГО') исключаются из классификации, т.к. у них тоже A пусто."""
        r = row_idx
        e = ABC_RANGE_END
        kind = (f'(($A$5:$A${e}="")=(A{r}=""))'
                f'*(ЛЕВСИМВ($B$5:$B${e};5)<>"ВСЕГО")')
        cum = f'СУММПРОИЗВ({kind}*($P$5:$P${e}>=P{r})*$P$5:$P${e})'
        total = f'СУММПРОИЗВ({kind}*$P$5:$P${e})'
        return (f'=ЕСЛИОШИБКА('
                f'ЕСЛИ({cum}/{total}<=0,8;"A";'
                f'ЕСЛИ({cum}/{total}<=0,95;"B";"C"))'
                f';"")')

    def abc_roi_formula(row_idx: int) -> str:
        """ABC по ROI (Парето 80/15/5). Главные и дубли — отдельно (A пуст у главных).
        ROI в колонке L. Если L пустой/не число — C. Секционные строки "ВСЕГО (…)"
        исключаются по колонке B."""
        r = row_idx
        e = ABC_RANGE_END
        kind = (f'(($A$5:$A${e}="")=(A{r}=""))'
                f'*(ЛЕВСИМВ($B$5:$B${e};5)<>"ВСЕГО")')
        cum = f'СУММПРОИЗВ({kind}*($L$5:$L${e}>=L{r})*$L$5:$L${e})'
        total = f'СУММПРОИЗВ({kind}*$L$5:$L${e})'
        return (f'=ЕСЛИ(НЕ(ЕЧИСЛО(L{r}));"C";'
                f'ЕСЛИОШИБКА('
                f'ЕСЛИ({cum}/{total}<=0,8;"A";'
                f'ЕСЛИ({cum}/{total}<=0,95;"B";"C"))'
                f';"C"))')

    # Пороги оборачиваемости для ABC-классификации.
    # Китай: длинный цикл поставок → мягкие пороги 30/45 дней.
    # Рынок: быстрый оборот → строгие пороги 10/15 дней.
    TURNOVER_THRESHOLDS = {
        True:  (15, 10),  # is_market → (hi_C, hi_B)
        False: (45, 30),  # china
    }
    TURNOVER_DESC = {
        True: ('< 10 дней оборачиваемости',
               '10–15 дней оборачиваемости',
               '> 15 дней или нет продаж'),
        False: ('< 30 дней оборачиваемости',
                '30–45 дней оборачиваемости',
                '> 45 дней или нет продаж'),
    }

    def abc_turnover_formula(row_idx: int, is_market: bool = False) -> str:
        """ABC по оборачиваемости (колонка J). Для Рынка строже (10/15), для Китая мягче
        (30/45). Если в J не число (нет заказов → ""), класс = C."""
        r = row_idx
        hi_c, hi_b = TURNOVER_THRESHOLDS[is_market]
        return (f'=ЕСЛИ(НЕ(ЕЧИСЛО(J{r}));"C";'
                f'ЕСЛИ(J{r}>{hi_c};"C";ЕСЛИ(J{r}>{hi_b};"B";"A")))')

    def abc_description_formula(row_idx: int, is_market: bool = False) -> str:
        """Формульная Расшифровка. Склеивает значения AB/AC/AD + текстовые описания.
        Если хоть одна из ABC-ячеек пустая — пустая строка.
        Текст описания оборачиваемости зависит от Рынок/Китай (разные пороги)."""
        r = row_idx
        turn_a, turn_b, turn_c = TURNOVER_DESC[is_market]
        rev = (f'SWITCH(AB{r};"A";"ТОП 80% выручки";"B";"доп. 15% выручки";'
               f'"C";"хвост 5% выручки";"")')
        roi = (f'SWITCH(AC{r};"A";"ТОП 80% ROI";"B";"доп. 15% ROI";'
               f'"C";"хвост 5% ROI";"")')
        turn = (f'SWITCH(AD{r};"A";"{turn_a}";"B";"{turn_b}";"C";"{turn_c}";"")')
        return (f'=ЕСЛИ(ИЛИ(AB{r}="";AC{r}="";AD{r}="");"";'
                f'AB{r}&AC{r}&AD{r}&": "&{rev}&", "&{roi}&", "&{turn})')

    def gmroi_week_formula(row_idx: int) -> str:
        """Недельный GMROI = profit / Стоимость стока (R).
        profit = P - Q - S - T - U - V - W - X - Y (R не входит — это стоимость стока).
        R уже содержит формулу (F+Z)/2*(Q/AA) на уровне строки, а на уровне тоталов
        R = СУММЕСЛИ по мейнам — так на портфеле не происходит переоценки стока
        через средневзвешенный себес."""
        r = row_idx
        return (f'=ЕСЛИОШИБКА('
                f'(P{r}-Q{r}-S{r}-T{r}-U{r}-V{r}-W{r}-X{r}-Y{r})'
                f'/R{r}'
                f';"")')

    def gmroi_month_formula(row_idx: int) -> str:
        return f'=ЕСЛИ(N{row_idx}="";"";N{row_idx}*52/12)'

    def gmroi_year_formula(row_idx: int) -> str:
        return f'=ЕСЛИ(N{row_idx}="";"";N{row_idx}*52)'

    # Хелперы для сборки ячеек строк (используются ниже в главном цикле).
    def components_cells(comps: dict | None) -> list:
        """9 столбцов P..X: Выручка, Себес, Комиссия, Эквайринг, Логистика, Хранение,
        Реклама, Прочее, Налог."""
        if not comps:
            return [''] * 9
        return [comps['sale'], comps['cost'], comps['commission'], comps['acquiring'],
                comps['logistics'], comps['storage'], comps['advertising'],
                comps['other'], comps['tac']]

    def quantities_cell(comps: dict | None):
        """Колонка Z — Кол-во продаж за неделю."""
        return '' if not comps else comps['quantities']

    # Макет листа:
    #   row 1-2 — шапка (закреп)
    #   row 3   — "ВСЕГО (мейны)"  (закреп) — сумма = row 4 + row {china_section_row}
    #   row 4   — "ВСЕГО (Рынок)"  (секционный подзаголовок, НЕ закреплён)
    #   row 5..M — Рынок (мейны + дубли)
    #   row M+1 — "ВСЕГО (Китай)" (секционный подзаголовок)
    #   row M+2..N — Китай (мейны + дубли)
    market_rows_total = sum(1 + len(dubs) for _, _, dubs in market_data)
    china_rows_total = sum(1 + len(dubs) for _, _, dubs in china_data)
    market_section_row = 4            # сразу под закреплённой строкой 3 (ВСЕГО мейны)
    market_data_start = 5
    market_data_end = market_section_row + market_rows_total  # =4 если нет данных
    china_section_row = market_data_end + 1
    china_data_start = china_section_row + 1
    china_data_end = china_section_row + china_rows_total     # =china_section_row если пусто

    def _row_formulas(self_row: int, tsum) -> list:
        """Общая часть любой строки тоталов: Оборач./Маржа/ROI/GMROI/суммы по колонкам.
        tsum(letter) — функция, возвращающая формулу суммы для столбца."""
        r = self_row
        row: list = []
        row.extend(tsum(c) for c in ('C', 'D', 'E', 'F', 'G', 'H'))
        row.append(f'=ЕСЛИ(G{r}=0;"";ОКРУГЛ(F{r}/G{r};0))')
        row.append(f'=ЕСЛИ(H{r}=0;"";ОКРУГЛ(F{r}*7/H{r};0))')
        row.append(margin_formula(r))
        row.append(roi_formula(r))
        row.append(gmroi_year_formula(r))
        row.append(gmroi_week_formula(r))
        row.append(gmroi_month_formula(r))
        row.extend(tsum(c) for c in ('P', 'Q'))
        row.append(tsum('R'))
        row.extend(tsum(c) for c in ('S', 'T', 'U', 'V', 'W', 'X', 'Y'))
        row.extend(tsum(c) for c in ('Z', 'AA'))
        return row

    def _build_grand_totals(label: str, self_row: int, msec: int, csec: int) -> list:
        """Row 3 "ВСЕГО (мейны)": просто сумма двух секционных строк (Рынок + Китай)."""
        row: list = ['', label] + _row_formulas(self_row, lambda c: f'={c}{msec}+{c}{csec}')
        row.extend([''] * (34 - len(row)))
        return row

    def _build_section_totals(label: str, self_row: int, start: int, end: int) -> list:
        """Секционный подзаголовок (Рынок/Китай): SUMIF по ограниченному диапазону
        мейнов (A пусто). Если start > end — секция пуста, суммы остаются пустыми.
        A пусто; ABC-формулы отличают эту строку от мейна по колонке B
        (B начинается с "ВСЕГО...")."""
        is_empty = end < start

        def tsum(letter: str):
            if is_empty:
                return ''
            return f'=СУММЕСЛИ($A${start}:$A${end};"";{letter}${start}:{letter}${end})'

        row: list = ['', label] + _row_formulas(self_row, tsum)
        row.extend([''] * (34 - len(row)))
        return row

    totals_all = _build_grand_totals('ВСЕГО (мейны)', 3, market_section_row, china_section_row)
    totals_market = _build_section_totals('ВСЕГО (Рынок)', market_section_row,
                                          market_data_start, market_data_end)
    totals_china = _build_section_totals('ВСЕГО (Китай)', china_section_row,
                                         china_data_start, china_data_end)

    # Собираем data по макету: [шапка, grand, section_market, …market blocks…,
    # section_china, …china blocks…]
    data: list[list] = [headers1, headers2, totals_all, totals_market]
    dub_ranges: list[tuple[int, int]] = []
    # Какие строки — тоталы (grand + 2 секционных). Нужно для форматирования.
    totals_row_indices: list[int] = [3, market_section_row, china_section_row]
    logger.info('[7/7] Собираю строки Недельки: блоков рынок=%d (строк 5..%d), '
                'китай=%d (строк %d..%d)',
                len(market_data), market_data_end,
                len(china_data), china_data_start, china_data_end)

    _china_section_inserted = False
    for main_vendor, related, dub_rows_data in (market_data + china_data):
        # Между Рынком и Китаем вставляем секционный подзаголовок "ВСЕГО (Китай)".
        if not _china_section_inserted and (len(data) + 1) == china_section_row:
            data.append(totals_china)
            _china_section_inserted = True
        # Маркер мейна — для выбора порогов ABC-оборачиваемости и текста расшифровки.
        is_market = main_marker.get(main_vendor) == 'market'
        agg_row = len(data) + 1
        first_dub = agg_row + 1
        last_dub = agg_row + len(dub_rows_data)
        dub_ranges.append((first_dub, last_dub))

        def col_sum(letter):
            return "=СУММ(" + ";".join(f"{letter}{r}" for r in range(first_dub, last_dub + 1)) + ")"

        # FBS главного берётся формулой из листа 'ТО сегодня' (O+Q) — см. fbs_formula.
        comment_main, qty_main, days_main = supply_for(main_vendor)

        # Компоненты прибыли: P, Q — Выручка/Себес (сумма); R — Стоимость стока (helper,
        # формула per-row); S..Y — 7 остальных компонентов (сумма); Z — Сток на начало
        # (формула из 'ТО -7'); AA — Кол-во продаж (сумма).
        data.append([
            '', main_vendor,
            fbo_formula(agg_row),                      # C = FBO (формула из 'ТО сегодня' C+F+I+L)
            fbs_formula(agg_row),                      # D = FBS (формула из 'ТО сегодня' O+Q)
            priyomka_formula(agg_row),                 # E = Приёмка (только у мейна)
            f"=СУММ(C{agg_row};D{agg_row};E{agg_row})",  # F = Итого (FBO+FBS+Приёмка)
            col_sum("G"),                              # G = Вчера заказы
            col_sum("H"),                              # H = Неделя заказы
            f'=ЕСЛИ(G{agg_row}=0;"";ОКРУГЛ(F{agg_row}/G{agg_row};0))',   # I = Оборач. Вчера
            f'=ЕСЛИ(H{agg_row}=0;"";ОКРУГЛ(F{agg_row}*7/H{agg_row};0))', # J = Оборач. Неделя
            margin_formula(agg_row),                   # K = Маржа
            roi_formula(agg_row),                      # L = ROI
            gmroi_year_formula(agg_row),               # M = GMROI год
            gmroi_week_formula(agg_row),               # N = GMROI неделя
            gmroi_month_formula(agg_row),              # O = GMROI месяц
            col_sum("P"),                              # P = Выручка
            col_sum("Q"),                              # Q = Себес
            stock_value_formula(agg_row),              # R = Стоимость стока (helper)
            col_sum("S"),                              # S = Комиссия
            col_sum("T"),                              # T = Эквайринг
            col_sum("U"),                              # U = Логистика
            col_sum("V"),                              # V = Хранение
            col_sum("W"),                              # W = Реклама
            col_sum("X"),                              # X = Прочее
            col_sum("Y"),                              # Y = Налог
            stock_start_main_formula(agg_row),         # Z = Сток на начало (из 'ТО -7' R)
            col_sum("AA"),                             # AA = Кол-во продаж
            abc_revenue_formula(agg_row),              # AB = ABC выручка
            abc_roi_formula(agg_row),                  # AC = ABC ROI
            abc_turnover_formula(agg_row, is_market),  # AD = ABC оборач.
            abc_description_formula(agg_row, is_market),  # AE = Расшифровка
            days_main, qty_main,                       # AF, AG = Ближайшая поставка
            comment_main,                              # AH = Комментарий
        ])

        for d in dub_rows_data:
            row_idx = len(data) + 1
            shop_combined = f"{d['mp']} {d['shop']}".strip() if d['mp'] or d['shop'] else ''
            comps = components_cells(d['comps'])  # 9 значений: sale, cost, 7 остальных
            data.append([
                shop_combined, d['vendor'],
                d['fbo_qty'], '',                          # C=FBO, D=FBS (пусто у дубля)
                '',                                        # E = Приёмка — только у мейна
                f"=C{row_idx}",                            # F = Итого (только FBO у дубля)
                d['yest_qty'],                             # G = Вчера
                d['week_qty'],                             # H = Неделя
                f'=ЕСЛИ(G{row_idx}=0;"";ОКРУГЛ(F{row_idx}/G{row_idx};0))',
                f'=ЕСЛИ(H{row_idx}=0;"";ОКРУГЛ(F{row_idx}*7/H{row_idx};0))',
                margin_formula(row_idx),
                roi_formula(row_idx),
                gmroi_year_formula(row_idx),
                gmroi_week_formula(row_idx),
                gmroi_month_formula(row_idx),
                comps[0],                                  # P = Выручка
                comps[1],                                  # Q = Себес
                stock_value_formula(row_idx),              # R = Стоимость стока
                *comps[2:],                                # S..Y = 7 остальных компонентов
                d['stock_start'],                          # Z = Сток на начало
                quantities_cell(d['comps']),               # AA = Кол-во продаж
                abc_revenue_formula(row_idx),              # AB
                abc_roi_formula(row_idx),                  # AC
                abc_turnover_formula(row_idx, is_market),  # AD — пороги такие же как у мейна
                abc_description_formula(row_idx, is_market),  # AE
                '', '',  # AF, AG — Ближайшая поставка только на агрегатной строке
                '',       # AH — Комментарий только на агрегатной строке
            ])

    # Если Китая не было (цикл не триггернул вставку) — всё равно показываем заголовок
    # "ВСЕГО (Китай)" с пустыми суммами, для единообразия макета.
    if not _china_section_inserted:
        data.append(totals_china)

    # КРИТИЧНО: снимаем мерджи в шапке ПЕРЕД worksheet.update() — иначе значения,
    # попадающие в ячейки уже существующего merge с прошлого прогона, уходят только
    # в top-left, остальные клетки остаются пустыми (потом видны "пропавшие" Заказы,
    # Оборачиваемость, Показатели и т.д.).
    spreadsheet.batch_update({"requests": [{"unmergeCells": {"range": {
        "sheetId": worksheet_week.id,
        "startRowIndex": 0,
        "endRowIndex": 2,
        "startColumnIndex": 0,
    }}}]})

    logger.info('Собрано: блоков с данными %d, строк всего %d (вкл. 2 шапки + тоталы)',
                len(dub_ranges), len(data))

    logger.info('Очищаю лист "%s" и записываю данные...', WEEK)
    worksheet_week.clear()
    worksheet_week.update(range_name='A1', values=data, value_input_option=ValueInputOption("USER_ENTERED"))

    logger.info('Применяю форматирование...')
    market_data_range = (market_data_start, market_data_end) if market_rows_total else None
    china_data_range = (china_data_start, china_data_end) if china_rows_total else None
    format_week_sheet(worksheet=worksheet_week,
                      spreadsheet=spreadsheet,
                      headers1=headers1,
                      headers2=headers2,
                      dub_ranges=dub_ranges,
                      totals_row_indices=totals_row_indices,
                      section_row_indices=[market_section_row, china_section_row],
                      market_data_range=market_data_range,
                      china_data_range=china_data_range)
    logger.info('=== update_week_sheet: готово ===')


def main(retries: int = 6) -> None:
    try:
        db_conn = DbConnection()
        db_conn.start_db()

        stat_orders_update(db_conn=db_conn, days=1)
        update_week_sheet(db_conn=db_conn)
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            time.sleep(10)
            main(retries=retries - 1)
    except gspread.exceptions.APIError as e:
        logger.error(f'Ошибка работы с GoogleSheet: {e}. Осталось попыток: {retries - 1}')
        if retries > 0:
            time.sleep(60)
            main(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    main()
