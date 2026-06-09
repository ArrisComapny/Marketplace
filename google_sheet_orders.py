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

    keep = [SAMPLE, WEEK]

    # исключаем "Шаблон" из фильтрации, он всегда сохраняется
    filtered = [ws for ws in sheets if ws.title not in keep]

    # если больше n, удаляем лишние
    if len(filtered) > n:
        for ws in filtered[n:]:
            spreadsheet.del_worksheet(ws)


def reorder_sheets(spreadsheet: gspread.Spreadsheet) -> None:
    """Реорганизация листов с сохранением шаблона в начале."""
    sheets = {sheet.title: sheet.id for sheet in spreadsheet.worksheets()}
    desired_order = list(sheets.keys())
    desired_order.remove(SAMPLE)
    desired_order.remove(WEEK)
    desired_order.sort(reverse=True, key=lambda x: (x.split(" копия")[0], "копия" not in x))
    desired_order = [SAMPLE, WEEK] + desired_order

    all_requests = []
    for index, sheet_name in enumerate(desired_order):
        sheet_id = sheets.get(sheet_name)
        if sheet_id is not None:
            all_requests.append({"updateSheetProperties": {"properties": {"sheetId": sheet_id, "index": index},
                                                       "fields": "index"}})
    if requests:
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
                      headers1: list, headers2: list, dub_ranges: list[tuple[int, int]]) -> None:
    """Форматирование листа Неделька: мерджи шапки, заморозка, выравнивание, группировки."""
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

    # Закрепляем первые две строки и первые две колонки (Магазин + Артикул)
    all_requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 2}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
    }})

    # Ширина колонок:
    #   A=100 (Магазин), B=190 (Артикул),
    #   C-I=60 (Стоки/Заказы/Оборачиваемость),
    #   J-N=70 (Маржа + ROI + три GMROI),
    #   O-Y=80 (9 компонентов + Сток на начало + Кол-во продаж),
    #   Z-AB=70 (три ABC), AC=400 (Расшифровка), AD-AE=60 (Ближайшая поставка),
    #   AF=120 (Комментарий).
    column_widths = [(0, 1, 100), (1, 2, 190), (2, 9, 60),
                     (9, 14, 70), (14, 25, 80), (25, 28, 70),
                     (28, 29, 400), (29, 31, 60), (31, 32, 120)]
    for start_col, end_col, width in column_widths:
        all_requests.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id,
                                                                     "dimension": "COLUMNS",
                                                                     "startIndex": start_col,
                                                                     "endIndex": end_col},
                                                           "properties": {"pixelSize": width},
                                                           "fields": "pixelSize"}})

    # Выравнивание по центру всех колонок кроме первых двух (C..AF, включая Расшифровку
    # и Комментарий).
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 2,
                                                  "endColumnIndex": 32},
                                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat.horizontalAlignment"}})

    # Перенос текста для Расшифровки (AC=28) — там длинная подсказка по ABC.
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 28,
                                                  "endColumnIndex": 29},
                                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                                        "fields": "userEnteredFormat.wrapStrategy"}})

    # Вертикальное выравнивание по центру для всех ячеек листа
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id},
                                        "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE"}},
                                        "fields": "userEnteredFormat.verticalAlignment"}})

    # Условное форматирование трёх колонок ABC (Z..AB, индексы 25..28):
    # A=зелёный, B=жёлтый, C=красный
    for value, color in (('A', COLOR_ABC_A), ('B', COLOR_ABC_B), ('C', COLOR_ABC_C)):
        all_requests.append({"addConditionalFormatRule": {
            "rule": {"ranges": [{"sheetId": sheet_id,
                                 "startRowIndex": 2,
                                 "startColumnIndex": 25,
                                 "endColumnIndex": 28}],
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

    # Числовой формат #,##0 для C..I (Стоки/Заказы/Оборачиваемость)
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 2,
                                                  "endColumnIndex": 9},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER",
                                                                                        "pattern": "#,##0"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})

    # Процентный формат для Маржа + ROI + три GMROI (J..N)
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 9,
                                                  "endColumnIndex": 14},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT",
                                                                                        "pattern": "0.00%"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})

    # Числовой формат #,##0 для O..Y (9 компонентов + Сток на начало + Кол-во продаж)
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 14,
                                                  "endColumnIndex": 25},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER",
                                                                                        "pattern": "#,##0"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})

    # Числовой формат #,##0 для AD..AE (Ближайшая поставка: Дней до / Кол-во).
    # AC (28) — Расшифровка, текст, в этот диапазон не входит.
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 2,
                                                  "startColumnIndex": 29,
                                                  "endColumnIndex": 31},
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

    # Группируем GMROI неделя + GMROI месяц (M..N, 12..14) и сворачиваем по умолчанию
    range_gmroi = {"sheetId": sheet_id,
                   "dimension": "COLUMNS",
                   "startIndex": 12,
                   "endIndex": 14}
    all_requests.append({"addDimensionGroup": {"range": range_gmroi}})
    all_requests.append({"updateDimensionProperties": {"range": range_gmroi,
                                                       "properties": {"hiddenByUser": True},
                                                       "fields": "hiddenByUser"}})

    # Группируем компоненты + Сток на начало + Кол-во продаж (O..Y, 14..25) и сворачиваем
    range_cols = {"sheetId": sheet_id,
                  "dimension": "COLUMNS",
                  "startIndex": 14,
                  "endIndex": 25}
    all_requests.append({"addDimensionGroup": {"range": range_cols}})
    all_requests.append({"updateDimensionProperties": {"range": range_cols,
                                                       "properties": {"hiddenByUser": True},
                                                       "fields": "hiddenByUser"}})

    # Группируем Расшифровку (AC, 28..29) и сворачиваем — широкая колонка с подсказкой,
    # удобно скрывать по умолчанию.
    range_desc = {"sheetId": sheet_id,
                  "dimension": "COLUMNS",
                  "startIndex": 28,
                  "endIndex": 29}
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
        #   right Артикул (B=1), right Итого стоков (E=4),
        #   right Неделя заказов (G=6), right Неделя оборач. (I=8),
        #   right GMROI год (L=11), right ABC оборач. (AB=27),
        #   left Дней до (AD=29) — отделяет Ближайшую поставку.
        thin_black = {"style": "SOLID", "width": 1,
                      "color": {"red": 0, "green": 0, "blue": 0}}
        vertical_lines = [(1, 'right'), (4, 'right'), (6, 'right'),
                          (8, 'right'), (11, 'right'), (27, 'right'),
                          (29, 'left')]
        for col_idx, side in vertical_lines:
            group_requests.append({"updateBorders": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": 2,
                          "endRowIndex": last_data_row,
                          "startColumnIndex": col_idx,
                          "endColumnIndex": col_idx + 1},
                side: thin_black,
            }})
        # Создаём row-groups для дублей.
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
    spreadsheet = initialize_google_sheet()

    worksheet_week = spreadsheet.worksheet(WEEK)
    worksheet_sample = spreadsheet.worksheet(SAMPLE)

    headers1 = ["", "", "Стоки", "", "", "Заказы", "", "Оборачиваемость", "",
                "Показатели", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
                "Ближайшая поставка", "",
                ""]
    headers2 = [
        "Магазин", "Артикул", "FBO", "FBS", "Итого", "Вчера", "Неделя",
        "Вчера", "Неделя",
        "Маржа", "ROI",
        "GMROI год", "GMROI неделя", "GMROI месяц",
        "Выручка", "Себес", "Комиссия", "Эквайринг",
        "Логистика", "Хранение", "Реклама", "Прочее", "Налог",
        "Сток на начало", "Кол-во продаж",
        "ABC выручка", "ABC ROI", "ABC оборач.", "Расшифровка",
        "Дней до", "Кол-во",
        "Комментарий",
    ]

    # vendors_map_ci — case-insensitive: ключ и main_vendor приведены к нижнему регистру.
    # В шаблоне артикулы могут быть в любом регистре (например "5002/5Лопрыск"), а в БД
    # они нормализованы в lower — сравниваем без учёта регистра.
    vendors_map_raw = db_conn.get_vendors_map()
    vendors_map: dict[str, tuple[str, str]] = {
        k.lower(): ((v[0] or '').lower(), v[1]) for k, v in vendors_map_raw.items()
    }

    # Читаем колонки шаблона A..D одним запросом: A=Артикул, B=Комментарий, C=Кол-во, D=Дата прихода
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

    # Группируем артикулы по главному: {main_vendor: [главный, ...дубли]}
    blocks: dict[str, list[str]] = {}
    for vendor in template_vendors:
        main_vendor, type_vendor = vendors_map[vendor]
        if type_vendor == 'main':
            blocks.setdefault(vendor, [])
            if vendor not in blocks[vendor]:
                blocks[vendor].insert(0, vendor)
        elif type_vendor == 'maindouble':
            blocks.setdefault(main_vendor, [])
            blocks[main_vendor].append(vendor)

    # Главный — первой строкой блока
    for main_vendor, related in blocks.items():
        if main_vendor in related:
            blocks[main_vendor] = [main_vendor] + [v for v in related if v != main_vendor]

    # Полная группа артикулов по каждому мейну (из vendors_map), включая варианты,
    # которых нет в шаблоне. FBS — общий пул на группу: в БД он может лежать под
    # артикулом мейна или любого варианта. Если мейна нет в шаблоне, в related его
    # тоже нет, и FBS под мейном терялся — поэтому FBS суммируем по всей группе.
    main_to_members: dict[str, set[str]] = {}
    for _v, (_mv, _tv) in vendors_map.items():
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
    stocks = db_conn.get_stocks_detail(from_date=today)
    stock_map: dict[tuple[str, str], int] = {}
    for s in stocks:
        key = (s.client, (s.vendor_code or '').lower())
        stock_map[key] = stock_map.get(key, 0) + s.quantity

    # Сток на начало периода (фактический снимок неделю назад).
    stocks_start = db_conn.get_stocks_detail(from_date=today - timedelta(days=7))
    stock_start_map: dict[tuple[str, str], int] = {}
    for s in stocks_start:
        key = (s.client, (s.vendor_code or '').lower())
        stock_start_map[key] = stock_start_map.get(key, 0) + s.quantity

    # Заказы: вчера и за последние 7 дней (по день, кончая вчерашним)
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=7)
    yesterday_orders = db_conn.get_orders(from_date=yesterday)
    week_orders = db_conn.get_orders(from_date=week_start, to_date=yesterday)

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

    clients = {c.client_id: c for c in db_conn.get_clients()}

    # Прибыль за неделю с разбивкой: (client_id, vendor_lower) -> dict со всеми статьями
    PROFIT_FIELDS = ('sale', 'cost', 'commission', 'acquiring',
                     'logistics', 'storage', 'advertising', 'other', 'tac',
                     'quantities', 'profit')
    profit_records = db_conn.get_profit(from_date=week_start, to_date=yesterday)
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

    # Считаем метрики блока (главный + дубли): revenue, profit, cost, current_stock, week_orders.
    # Суммируем по всем магазинам, на которых живёт каждый артикул из блока.
    block_revenue: dict[str, float] = {}
    block_profit: dict[str, float] = {}
    block_cost: dict[str, float] = {}
    block_stock_now: dict[str, int] = {}
    block_week_orders: dict[str, int] = {}
    for main_vendor, related in blocks.items():
        rev = prof = cost = 0.0
        stock = orders = 0
        # FBS-пул — общий на всю группу (мейн может отсутствовать в шаблоне).
        for v in fbs_members(main_vendor, related):
            stock += stock_map.get(('FBS', v), 0)
        for v in related:
            for cid in vendor_clients.get(v, ()):
                s = profit_map.get((cid, v.lower()))
                if s:
                    rev += s['sale']
                    prof += s['profit']
                    cost += s['cost']
                stock += stock_map.get((cid, v), 0)
                orders += week_map.get((cid, v), 0)
        block_revenue[main_vendor] = rev
        block_profit[main_vendor] = prof
        block_cost[main_vendor] = cost
        block_stock_now[main_vendor] = stock
        block_week_orders[main_vendor] = orders

    block_rev_classes = _classify_pareto([(mv, block_revenue[mv]) for mv in blocks])

    # ROI блока = profit / cost. Парето 80/15/5 — как у выручки.
    block_roi = {mv: (block_profit[mv] / block_cost[mv] if block_cost[mv] > 0 else 0)
                 for mv in blocks}
    block_roi_classes = _classify_pareto([(mv, block_roi[mv]) for mv in blocks])

    # Метрики и ABC-классы дублей (для отдельной Парето-классификации по (vendor, client)).
    dub_rev: dict[tuple[str, str], float] = {}
    dub_profit: dict[tuple[str, str], float] = {}
    dub_cost: dict[tuple[str, str], float] = {}
    dub_stock_now: dict[tuple[str, str], int] = {}
    dub_week_orders: dict[tuple[str, str], int] = {}
    for main_vendor, related in blocks.items():
        for v in related:
            for cid in vendor_clients.get(v, ()):
                key = (v, cid)
                s = profit_map.get((cid, v)) or {}
                dub_rev[key] = s.get('sale', 0.0)
                dub_profit[key] = s.get('profit', 0.0)
                dub_cost[key] = s.get('cost', 0.0)
                dub_stock_now[key] = stock_map.get((cid, v), 0)  # FBO у магазина (без FBS)
                dub_week_orders[key] = week_map.get((cid, v), 0)

    dub_rev_classes = _classify_pareto([(k, dub_rev[k]) for k in dub_rev])
    dub_roi = {k: (dub_profit[k] / dub_cost[k] if dub_cost[k] > 0 else 0) for k in dub_rev}
    dub_roi_classes = _classify_pareto([(k, dub_roi[k]) for k in dub_rev])

    def _dub_turnover_class(key: tuple[str, str]) -> str:
        orders = dub_week_orders.get(key, 0)
        if orders <= 0:
            return 'C'
        stock = dub_stock_now.get(key, 0)
        days = round(stock * 7 / orders)
        return 'C' if days > 45 else ('B' if days > 30 else 'A')

    # Расшифровка ABC: тройка букв + краткое объяснение каждой части.
    DESC_REV = {'A': 'ТОП 80% выручки', 'B': 'доп. 15% выручки', 'C': 'хвост 5% выручки'}
    DESC_ROI = {'A': 'ТОП 80% ROI', 'B': 'доп. 15% ROI', 'C': 'хвост 5% ROI'}
    DESC_TURN = {'A': '< 30 дней оборачиваемости',
                 'B': '30–45 дней оборачиваемости',
                 'C': '> 45 дней или нет продаж'}

    def abc_description(a: str, b: str, c: str) -> str:
        if not (a and b and c):
            return ''
        return f"{a}{b}{c}: {DESC_REV.get(a, '?')}, {DESC_ROI.get(b, '?')}, {DESC_TURN.get(c, '?')}"

    def _block_turnover_class(mv: str) -> str:
        orders = block_week_orders.get(mv, 0)
        if orders <= 0:
            return 'C'  # нет заказов — оборачиваемость не считается, кладём в C
        stock = block_stock_now.get(mv, 0)
        days = round(stock * 7 / orders)
        return 'C' if days > 45 else ('B' if days > 30 else 'A')

    abc_order = {'A': 0, 'B': 1, 'C': 2}
    blocks = dict(sorted(
        blocks.items(),
        key=lambda kv: (abc_order.get(block_rev_classes.get(kv[0], ''), 3),
                        abc_order.get(block_roi_classes.get(kv[0], ''), 3),
                        abc_order.get(_block_turnover_class(kv[0]), 3),
                        -block_revenue.get(kv[0], 0.0)),
    ))

    def components_for_vendor(vendor: str, client_id: str) -> dict | None:
        return profit_map.get((client_id, vendor.lower()))

    def stock_start_for_dub(vendor: str, client_id: str) -> int:
        """Сток FBO на начало периода для дубля (без FBS-пула)."""
        if not client_id:
            return 0
        return stock_start_map.get((client_id, vendor), 0)

    def stock_start_for_main(related_vendors, main_vendor) -> int:
        """Сток на начало для главного: FBO по магазинам (related) + FBS-пул по группе."""
        total = 0
        # FBS-пул на начало — по всей группе (мейн может отсутствовать в шаблоне).
        for v in fbs_members(main_vendor, related_vendors):
            total += stock_start_map.get(('FBS', v), 0)
        for v in related_vendors:
            for cid in vendor_clients.get(v, ()):
                total += stock_start_map.get((cid, v), 0)
        return total

    # Диапазон для SUMPRODUCT в ABC-формулах: рассчитаем как 2 шапки + достаточный запас.
    # Точный нижний индекс мы узнаем только после сборки data, поэтому фиксируем верхнюю
    # границу в 10000 — это безопасно для типичных объёмов и допустимо в Sheets.
    ABC_RANGE_END = 10000

    def margin_formula(row_idx: int) -> str:
        """Маржа в колонке J = profit / Выручка. Компоненты O..W, Выручка в O."""
        r = row_idx
        profit = f'(O{r}-P{r}-Q{r}-R{r}-S{r}-T{r}-U{r}-V{r}-W{r})'
        return f'=ЕСЛИОШИБКА({profit}/O{r};"")'

    def roi_formula(row_idx: int) -> str:
        """ROI в колонке K = profit / Себес. Компоненты O..W, Себес в P."""
        r = row_idx
        profit = f'(O{r}-P{r}-Q{r}-R{r}-S{r}-T{r}-U{r}-V{r}-W{r})'
        return f'=ЕСЛИОШИБКА({profit}/P{r};"")'

    def abc_revenue_formula(row_idx: int) -> str:
        """ABC по выручке (Парето 80/15/5). Главные и дубли — отдельно (A пуст у главных,
        там нет Магазина; у дублей в A стоит "WB Voyor" и т.п.). Выручка в колонке O."""
        r = row_idx
        e = ABC_RANGE_END
        kind = f'(($A$3:$A${e}="")=(A{r}=""))'
        cum = f'СУММПРОИЗВ({kind}*($O$3:$O${e}>=O{r})*$O$3:$O${e})'
        total = f'СУММПРОИЗВ({kind}*$O$3:$O${e})'
        return (f'=ЕСЛИОШИБКА('
                f'ЕСЛИ({cum}/{total}<=0,8;"A";'
                f'ЕСЛИ({cum}/{total}<=0,95;"B";"C"))'
                f';"")')

    def abc_roi_formula(row_idx: int) -> str:
        """ABC по ROI (Парето 80/15/5). Главные и дубли — отдельно (A пуст у главных).
        ROI в колонке K. Если K пустой/не число — C."""
        r = row_idx
        e = ABC_RANGE_END
        kind = f'(($A$3:$A${e}="")=(A{r}=""))'
        cum = f'СУММПРОИЗВ({kind}*($K$3:$K${e}>=K{r})*$K$3:$K${e})'
        total = f'СУММПРОИЗВ({kind}*$K$3:$K${e})'
        return (f'=ЕСЛИ(НЕ(ЕЧИСЛО(K{r}));"C";'
                f'ЕСЛИОШИБКА('
                f'ЕСЛИ({cum}/{total}<=0,8;"A";'
                f'ЕСЛИ({cum}/{total}<=0,95;"B";"C"))'
                f';"C"))')

    def abc_turnover_formula(row_idx: int) -> str:
        """ABC по оборачиваемости: >45 C, >30 B, иначе A. Колонка I (Оборач. Неделя).
        Если в I нет числа (нет заказов → ""), класс = C."""
        r = row_idx
        return (f'=ЕСЛИ(НЕ(ЕЧИСЛО(I{r}));"C";'
                f'ЕСЛИ(I{r}>45;"C";ЕСЛИ(I{r}>30;"B";"A")))')

    def gmroi_week_formula(row_idx: int) -> str:
        """Недельный GMROI (база) — теперь в колонке M.

        profit            = O - P - Q - R - S - T - U - V - W (Выручка − все расходы)
        средний_сток      = (E + X) / 2 — среднее между текущим (E=Итого) и началом (X)
        себес_за_единицу  = P / Y (Себес / Кол-во продаж)
        """
        r = row_idx
        return (f'=ЕСЛИОШИБКА('
                f'(O{r}-P{r}-Q{r}-R{r}-S{r}-T{r}-U{r}-V{r}-W{r})'
                f'/((E{r}+X{r})/2*(P{r}/Y{r}))'
                f';"")')

    def gmroi_month_formula(row_idx: int) -> str:
        return f'=ЕСЛИ(M{row_idx}="";"";M{row_idx}*52/12)'

    def gmroi_year_formula(row_idx: int) -> str:
        return f'=ЕСЛИ(M{row_idx}="";"";M{row_idx}*52)'

    # Собираем строки таблицы
    data: list[list] = [headers1, headers2]
    dub_ranges: list[tuple[int, int]] = []

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

    for main_vendor, related in blocks.items():
        # Один артикул может жить на нескольких магазинах: формируем по строке-дублю
        # на КАЖДУЮ пару (vendor, client_id). Если магазинов не нашлось — одна строка
        # с пустым магазином (комментарий из шаблона может оправдать показ).
        dub_rows_data = []
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
                dub_rows_data.append({
                    'vendor': vendor, 'client_id': client_id, 'mp': mp, 'shop': shop,
                    'fbo_qty': fbo_qty, 'yest_qty': yest_qty, 'week_qty': week_qty,
                    'days_v': days_v, 'qty_v': qty_v, 'comment_v': comment_v,
                    'comps': components_for_vendor(vendor, client_id),
                    'stock_start': stock_start_for_dub(vendor, client_id),
                })

        if not dub_rows_data:
            continue  # все дубли пустые — пропускаем весь блок

        agg_row = len(data) + 1
        first_dub = agg_row + 1
        last_dub = agg_row + len(dub_rows_data)
        dub_ranges.append((first_dub, last_dub))

        def col_sum(letter):
            return "=СУММ(" + ";".join(f"{letter}{r}" for r in range(first_dub, last_dub + 1)) + ")"

        # FBS главного — по всей группе артикула (мейн может отсутствовать в шаблоне).
        fbs_total = sum(stock_map.get(('FBS', v), 0) for v in fbs_members(main_vendor, related))
        comment_main, qty_main, days_main = supply_for(main_vendor)

        # Компоненты прибыли O..W — суммой по дублям; X (Сток на начало) — Python value
        # (FBS-пул не выражается через сумму ячеек дублей); Y (Кол-во продаж) — суммой.
        component_sums = [col_sum(letter) for letter in "OPQRSTUVW"]
        main_x_start = stock_start_for_main(related, main_vendor)
        qty_sales_sum = col_sum("Y")

        data.append([
            '', main_vendor,
            col_sum("C"),
            fbs_total,
            f"=СУММ(C{agg_row};D{agg_row})",
            col_sum("F"),
            col_sum("G"),
            f'=ЕСЛИ(F{agg_row}=0;"";ОКРУГЛ(E{agg_row}/F{agg_row};0))',
            f'=ЕСЛИ(G{agg_row}=0;"";ОКРУГЛ(E{agg_row}*7/G{agg_row};0))',
            margin_formula(agg_row),
            roi_formula(agg_row),
            gmroi_year_formula(agg_row),
            gmroi_week_formula(agg_row),
            gmroi_month_formula(agg_row),
            *component_sums,
            main_x_start,
            qty_sales_sum,
            abc_revenue_formula(agg_row),
            abc_roi_formula(agg_row),
            abc_turnover_formula(agg_row),
            abc_description(block_rev_classes.get(main_vendor, ''),
                            block_roi_classes.get(main_vendor, ''),
                            _block_turnover_class(main_vendor)),
            days_main, qty_main,
            comment_main,
        ])

        for d in dub_rows_data:
            row_idx = len(data) + 1
            shop_combined = f"{d['mp']} {d['shop']}".strip() if d['mp'] or d['shop'] else ''
            data.append([
                shop_combined, d['vendor'],
                d['fbo_qty'], '',
                f"=C{row_idx}",
                d['yest_qty'],
                d['week_qty'],
                f'=ЕСЛИ(F{row_idx}=0;"";ОКРУГЛ(E{row_idx}/F{row_idx};0))',
                f'=ЕСЛИ(G{row_idx}=0;"";ОКРУГЛ(E{row_idx}*7/G{row_idx};0))',
                margin_formula(row_idx),
                roi_formula(row_idx),
                gmroi_year_formula(row_idx),
                gmroi_week_formula(row_idx),
                gmroi_month_formula(row_idx),
                *components_cells(d['comps']),
                d['stock_start'],
                quantities_cell(d['comps']),
                abc_revenue_formula(row_idx),
                abc_roi_formula(row_idx),
                abc_turnover_formula(row_idx),
                abc_description(dub_rev_classes.get((d['vendor'], d['client_id']), ''),
                                dub_roi_classes.get((d['vendor'], d['client_id']), ''),
                                _dub_turnover_class((d['vendor'], d['client_id']))),
                '', '',  # Ближайшая поставка — только на агрегатной строке
                '',       # Комментарий — только на агрегатной строке
            ])

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

    worksheet_week.clear()
    worksheet_week.update(range_name='A1', values=data, value_input_option=ValueInputOption("USER_ENTERED"))

    format_week_sheet(worksheet=worksheet_week,
                      spreadsheet=spreadsheet,
                      headers1=headers1,
                      headers2=headers2,
                      dub_ranges=dub_ranges)


def main(retries: int = 6) -> None:
    try:
        db_conn = DbConnection()
        db_conn.start_db()

        # stat_orders_update(db_conn=db_conn, days=1)
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
