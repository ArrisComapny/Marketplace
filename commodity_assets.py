import calendar
import datetime as dt
import logging
import os
import re
import time
from datetime import datetime, date, timedelta

import gspread
from gspread.utils import ValueInputOption
from gspread_formatting import (
    Color, CellFormat, BooleanRule, BooleanCondition,
    ConditionalFormatRule, GridRange, get_conditional_format_rules, format_cell_range)
from oauth2client.service_account import ServiceAccountCredentials
from sqlalchemy.exc import OperationalError
from googleapiclient.discovery import build

from config import SPREADSHEET_ID_REMAINING_STOCK_PURCHASE, SPREADSHEET_ID_12NA273
from data_classes import DataSupply, DataCommodityAsset
from database import DbConnection



logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(PROJECT_ROOT, 'templates', 'service-account-432709-1178152e9e49.json')
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]


# === Подключение к API Google Sheets ===
def connect_to_google_sheets(spreadsheet_id: str) -> gspread.Spreadsheet:
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet


# === Получаем все названия листов ===
def get_sheet_names(spreadsheet: gspread.Spreadsheet) -> list[str]:
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


# === Преобразуем дату в Google формат ===
def convert_date(x):
    if isinstance(x, str):
        x = datetime.strptime(x, '%Y-%m-%d').date()

    if isinstance(x, dt.date):
        epoch = dt.date(1899, 12, 30)
        delta = x - epoch
        return int(delta.days + (delta.seconds / 86400))

    return x

def column_to_letter(n: int) -> str:
    """Преобразует номер столбца (1-based) в буквенное обозначение, как в Google Sheets"""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result

# Форматирование листа Plan2
def format_plan_sale(worksheet_id: int, spreadsheet: gspread.Spreadsheet) -> None:

    all_requests = []
    #  Задаем тип данных для первого столбца
    all_requests.append({"repeatCell": {"range": {"sheetId": worksheet_id,
                                                  "startRowIndex": 1,
                                                  "startColumnIndex": 0,
                                                  "endColumnIndex": 1},
                                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE",
                                                                                        "pattern": "dd-mm-yyyy"}}},
                                        "fields": "userEnteredFormat.numberFormat"}})
    #  Форматируем заголовок
    all_requests.append({"repeatCell": {"range": {"sheetId": worksheet_id,
                                                  "startRowIndex": 0,
                                                  "endRowIndex": 1,
                                                  "startColumnIndex": 0,  # столбец H (supplies)
                                                  "endColumnIndex": 8},
                                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.4,
                                                                                           "green": 0.4,
                                                                                           "blue": 0.4},
                                                                       "textFormat": {"bold": True,
                                                                                      "foregroundColor": {
                                                                                          "red": 1.0,
                                                                                          "green": 1.0,
                                                                                          "blue": 1.0}},
                                                                       "horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat(backgroundColor,textFormat,"
                                                  "horizontalAlignment)"}})
    # Форматируем заголовок supplies
    all_requests.append({"repeatCell": {"range": {"sheetId": worksheet_id,
                                                  "startRowIndex": 0,  # первая строка (заголовок)
                                                  "endRowIndex": 1,
                                                  "startColumnIndex": 7,  # столбец H (supplies)
                                                  "endColumnIndex": 8},
                                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1.0,
                                                                                           "green": 0.9,
                                                                                           "blue": 0.0},
                                                                       "textFormat": {"bold": True,
                                                                                      "foregroundColor": {
                                                                                          "red": 0.0,
                                                                                          "green": 0.0,
                                                                                          "blue": 0.0}},
                                                                       "horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat(backgroundColor,textFormat,"
                                                  "horizontalAlignment)"}})
    # Задаем ширину столбцов
    all_requests.append({"updateDimensionProperties": {"range": {"sheetId": worksheet_id,
                                                                 "dimension": "COLUMNS",
                                                                 "startIndex": 0,  # первый столбец (A)
                                                                 "endIndex": 1},
                                                       "properties": {"pixelSize": 100},  # ширина в пикселях
                                                       "fields": "pixelSize"}})
    # Задаем ширину столбца vendor_code
    all_requests.append({"updateDimensionProperties": {"range": {"sheetId": worksheet_id,
                                                                 "dimension": "COLUMNS",
                                                                 "startIndex": 1,  # второй столбец (B)
                                                                 "endIndex": 2},
                                                       "properties": {"pixelSize": 150},  # ширина в пикселях
                                                       "fields": "pixelSize"}})

    spreadsheet.batch_update({"requests": all_requests})

def add_fbs_stocks(db_conn: DbConnection) -> None:
    list_assets = []
    list_supplies = []

    vendors = db_conn.get_vendors()

    today = date.today()
    pattern = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    spreadsheet = connect_to_google_sheets(SPREADSHEET_ID_REMAINING_STOCK_PURCHASE)
    sheet_names = get_sheet_names(spreadsheet)

    dates_sheet_names = []
    for name in sheet_names:
        name = name.strip()
        if pattern.match(name):
            try:
                # пытаемся распарсить дату, проверяя её корректность
                date_obj = datetime.strptime(name, "%d.%m.%Y").date()
                dates_sheet_names.append(date_obj)
            except ValueError:
                # если дата некорректная (например, 32.12.2024) — пропускаем
                pass

    latest = max(dates_sheet_names)

    # сравниваем недели (isocalendar возвращает кортеж: (год, номер_недели, день_недели))
    if not ((latest.isocalendar()[0] == today.isocalendar()[0]) and (
            latest.isocalendar()[1] == today.isocalendar()[1])):
        raise Exception("Invalid date")

    name_list = latest.strftime("%d.%m.%Y")
    logger.info(f"Считываем данные с листа: {name_list}")

    worksheet = spreadsheet.worksheet(name_list)
    data = worksheet.get_all_values()
    for row in data[2:]:
        if len(row) <= 52:
            continue

        vendor_code = row[1].strip().lower()
        for suffix in ['/m', '/м', '/s', '/l', '/xs', '/xl', '/2xl']:  # Удаляем  размер
            if vendor_code.endswith(suffix):
                vendor_code = vendor_code.removesuffix(suffix)
                break

        if vendor_code not in vendors:  # Проверка есть ли артикул в базе данных
            continue

        fbs_value = row[38].strip()
        try:
            fbs = int(fbs_value)  # --- получаем fbs ---
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

        list_assets.append(DataCommodityAsset(vendor_code=vendor_code, fbs=fbs, on_the_way=quantity, date=latest))

        if quantity:
            orientation_arrival_value = row[51].strip()
            orientation_arrival = sheets_date_to_date(orientation_arrival_value)  # Получаем дату через функцию.
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

    # logger.info(f'Количество записей: {len(list_assets)}')
    # db_conn.add_commodity_assets(list_assets=list_assets)
    #
    # logger.info(f'Количество записей: {len(list_supplies)}')
    # db_conn.add_supplies(list_supplies=list_supplies)

def plan_sale(db_conn: DbConnection):
    # 1) Данные из БД
    plan_sale_values = db_conn.get_plan_sale()

    # 2) Заголовки (сразу объявляем — будем использовать ниже)
    headers = ['date', 'vendor_code', 'quantity_plan', 'price_plan',
               'sum_price_plan', 'profit%', 'profit', 'supplies']

    # 3) Преобразуем список объектов в двумерный список для Sheets
    rows = [[
        convert_date(x.date),  # число (Excel serial), готово для форматирования как дата
        x.vendor_code,
        x.quantity_plan,
        x.price_plan,
        x.sum_price_plan,
        x.profit_proc,
        x.profit,
        x.supplies
    ] for x in plan_sale_values]
    # 4) Подключение к таблице и получение/создание листа
    spreadsheet = connect_to_google_sheets(SPREADSHEET_ID_12NA273)
    sheet_name = "Plan2"
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        # cols: по количеству заголовков (и немного запасом не нужно)
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=len(headers) + 5)

    # 5) Очистка листа перед записью
    total_rows = len(worksheet.get_all_values())
    if total_rows > 1:
        worksheet.insert_row([''], index=total_rows)
        worksheet.delete_rows(2, total_rows)
    worksheet.clear()

    body = {"requests": [{"updateCells": {"range": {"sheetId": worksheet.id},
                                          "fields": "userEnteredFormat"}}]}
    spreadsheet.batch_update(body)

    # 6) Вставляем заголовки + данные
    worksheet.insert_row(headers, 1)
    if rows:
        # value_input_option='RAW': числа не будут превращаться в текст
        worksheet.append_rows(rows, value_input_option=ValueInputOption.raw)

    # 7) Форматируем первый столбец как дату (Google Sheets UI увидит именно дату)
    format_plan_sale(worksheet.id, spreadsheet)

def create_12_na_273(db_conn: DbConnection):
    # Создание листа с ЦКП месяц и год
    month_names_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
        7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    plan = "Plan"

    rows = []
    row1 = ["Артикул", "Plan", "Аналитика"]
    row2 = [""] * len(row1)

    start_date = db_conn.get_last_date_commodity_assets()
    logger.info(f"Сбор таблицы 12 на 273 за дату {start_date}")

    sheet_name = f"ЦКП {month_names_ru[start_date.month]} {start_date.year}"  # sheet_name -> 'ЦКП Ноябрь 2025'

    spreadsheet = connect_to_google_sheets(SPREADSHEET_ID_12NA273)

    logger.info(f"Сбор данных из Шаблона")
    worksheet = spreadsheet.worksheet("Шаблон") # подключение к листу Шаблон
    data = worksheet.get_all_values() # вытаскиваем данные

    # Формируем списки из данных
    vendor_codes = [row[0] for row in data]

    # Создаем словари на основе списков
    logger.info(f"Получение данных из БД")
    vendor_plan = db_conn.get_plan(start_date)
    vendor_analytics = db_conn.get_analytics(start_date)
    metrics = db_conn.get_stocks(start_date)

    logger.info(f"Обработка данных")
    # Вычисляем месяц через два месяца вперёд
    end_month = start_date.month + 2
    end_year = start_date.year

    # Корректируем, если переход через декабрь
    if end_month > 12:
        end_month -= 12
        end_year += 1

    # Последний день через два месяца
    _, last_day = calendar.monthrange(end_year, end_month)
    end_date = date(end_year, end_month, last_day)

    # Генерируем все даты от start_date до end_date включительно
    delta = (end_date - start_date).days + 1
    dates = [(start_date + timedelta(days=i)).strftime("%d.%m.%Y") for i in range(delta)]
    # Определяем диапазон дат для их наименования
    date_objs = [datetime.strptime(d, "%d.%m.%Y").date() for d in dates]

    header = [""] * len(dates)
    current_month = date_objs[0].month
    header[0] = month_names_ru[current_month]

    for i, d in enumerate(date_objs[1:], start=1):
        if d.month != current_month:
            current_month = d.month
            header[i] = month_names_ru[current_month]
    row1.extend(header)
    row2.extend(dates)  # Добавляем даты в шапку
    rows.extend([row1,row2])

    for sheet_row, vendor in enumerate(vendor_codes, 3):  # цикл по строкам формул
        if not vendor or not vendor_plan.get(vendor):
            rows.append(["" * len(row1)])
            continue
        row3 = [vendor, vendor_plan.get(vendor, ""), vendor_analytics.get(vendor, ""), metrics.get(vendor, 0)]

        for number_col, _ in enumerate(dates[1:], start=len(row3) + 1):
            col = column_to_letter(number_col)
            col_left = column_to_letter(number_col - 1)

            formula = (
                f"=ЕСЛИ(И({col_left}{sheet_row}<0; СУММЕСЛИМН({plan}!$H:$H;{plan}!$A:$A;{col}$2;{plan}!$B:$B;$A{sheet_row})>0); "
                f"СУММЕСЛИМН({plan}!$H:$H;{plan}!$A:$A;{col}$2;{plan}!$B:$B;$A{sheet_row});"
                f"{col_left}{sheet_row}-СУММЕСЛИМН({plan}!$C:$C;{plan}!$A:$A;{col}$2;{plan}!$B:$B;$A{sheet_row})"
                f"+СУММЕСЛИМН({plan}!$H:$H;{plan}!$A:$A;{col}$2;{plan}!$B:$B;$A{sheet_row}))")
            row3.append(formula)

        rows.append(row3)

    logger.info(f"Записываем данные в табличку")
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20, index=1)

    total_rows = len(worksheet.get_all_values())
    if total_rows > 1:
        worksheet.insert_row([''], index=total_rows)
        worksheet.delete_rows(1, total_rows)

    worksheet.clear()  # Очищаем лист перед записью

    body = {"requests": [{"updateCells": {"range": {"sheetId": worksheet.id},
                                          "fields": "userEnteredFormat"}}]}
    spreadsheet.batch_update(body)


    # # 6) Вставляем заголовки + данные
    worksheet.insert_rows(rows, 1, value_input_option=ValueInputOption.user_entered)
    logger.info(f"Форматируем таблицу")
    format_12_na_273(worksheet, spreadsheet, rows,date_objs)
    logger.info(f"Запись закончена")

def format_12_na_273(worksheet: gspread.Worksheet, spreadsheet: gspread.Spreadsheet,rows: list,date_objs) -> None:

    #==============форматирование===============
    sheet_id = worksheet.id
    start_col = len([v for v in rows[1] if not v])
    rules = get_conditional_format_rules(worksheet)

    # ===== УСЛОВИЕ 1 =====
    # D3 > C3 → светло-голубой
    rule_blue = ConditionalFormatRule(
        ranges=[GridRange(
            sheetId=sheet_id,
            startRowIndex=2,  # строка 3 (индексация 0-based → 2)
            endRowIndex=len(rows),  # до 3-й строки (не включительно → оставляем 3)
            startColumnIndex=start_col + 1,  # колонка E (0=A,1=B,2=C,3=D,4=E)
            endColumnIndex=len(rows[2])  # до F, но F не включается → остаёмся в E
        )],
        booleanRule=BooleanRule(
            condition=BooleanCondition('CUSTOM_FORMULA', [f'={column_to_letter(start_col + 2)}3>{column_to_letter(start_col + 1)}3']),
            format=CellFormat(
                backgroundColor= Color(0.64, 0.76, 0.95) # Светло-голубой
            )))
    # ===== УСЛОВИЕ 2 =====
    # Меньше 300 → Красный
    rule_red = ConditionalFormatRule(
        ranges=[GridRange(
            sheetId=sheet_id,
            startRowIndex=2,  # строка 3
            endRowIndex=len(rows),
            startColumnIndex=start_col,  # всё ещё красим E3
            endColumnIndex=len(rows[2])
        )],
        booleanRule=BooleanRule(
            condition=BooleanCondition('NUMBER_LESS', ['300']),
            format=CellFormat(
                backgroundColor=Color(0.95, 0.78, 0.76) # Светло красный
            )))
    # ===== УСЛОВИЕ 3 =====
    # больше 300 → зелёный
    rule_green = ConditionalFormatRule(
        ranges=[GridRange(
            sheetId=sheet_id,
            startRowIndex=2,  # строка 3
            endRowIndex=len(rows),
            startColumnIndex=start_col,  # всё ещё красим E3
            endColumnIndex=len(rows[2])
        )],
        booleanRule=BooleanRule(
            condition=BooleanCondition('NUMBER_GREATER_THAN_EQ', ['300']),
            format=CellFormat(
                backgroundColor=Color(0.71, 0.88, 0.8) # светлозеленый
            )))
    # ===== УСЛОВИЕ 4 =====
    # Каждый понедельник окрашивается в серый цвет.
    rule_formula_monday = ConditionalFormatRule(
        ranges=[GridRange(
            sheetId=sheet_id,
            startRowIndex=  1,  # строка 3 (индексация 0-based → 2)
            endRowIndex= 2,  # до 3-й строки (не включительно → оставляем 3)
            startColumnIndex=start_col,  # колонка E (0=A,1=B,2=C,3=D,4=E)
            endColumnIndex=len(rows[2])  # до F, но F не включается → остаёмся в E
        )],
        booleanRule=BooleanRule(
            condition=BooleanCondition('CUSTOM_FORMULA',
                                       [f'=WEEKDAY({column_to_letter(start_col + 1)}2;2)=1']),
            format=CellFormat(
                backgroundColor=Color(0.8, 0.8, 0.8)  # Светло-серый понедельник
            )))

    all_requests = []

    # Задаем ширину столбцов
    all_requests.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id,
                                                                 "dimension": "COLUMNS",
                                                                 "startIndex": 0,  # первый столбец (Даты)
                                                                 "endIndex": len(rows[2])},
                                                       "properties": {"pixelSize": 50},  # ширина в пикселях
                                                       "fields": "pixelSize"}})

    all_requests.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id,
                                                                 "dimension": "COLUMNS",
                                                                 "startIndex": 0,  # первый столбец (A)
                                                                 "endIndex": 1},
                                                       "properties": {"pixelSize": 160},  # ширина в пикселях
                                                       "fields": "pixelSize"}})

    all_requests.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id,
                                                                 "dimension": "COLUMNS",
                                                                 "startIndex": 2,  # первый столбец (B)
                                                                 "endIndex": 3},
                                                       "properties": {"pixelSize": 350},  # ширина в пикселях
                                                       "fields": "pixelSize"}})

    # Форматируем заголовок Артикул и Аналитика
    all_requests.append({"repeatCell": {"range": {"sheetId": sheet_id,
                                                  "startRowIndex": 0,  # первая строка (заголовок)
                                                  "endRowIndex": 1,
                                                  "startColumnIndex": 0,  # столбец H (supplies)
                                                  "endColumnIndex": len(rows[2])},
                                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True,
                                                                                      "foregroundColor": {
                                                                                          "red": 0.0,
                                                                                          "green": 0.0,
                                                                                          "blue": 0.0}},
                                        "horizontalAlignment": "CENTER",
                                        "verticalAlignment": "MIDDLE"}},
                                        "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)"}})
    # Закрепляем колонку A
    spreadsheet.batch_update({ "requests": [{"updateSheetProperties": {"properties": {
                                                                        "sheetId": worksheet.id,
                                                                        "gridProperties": {
                                                                        "frozenColumnCount": 1}},
                                                                        "fields": "gridProperties.frozenColumnCount"}}]})

    all_requests.append({"updateBorders": {"range": {"sheetId": sheet_id,
                                                     "startRowIndex": 0,  # строка 3 (нумерация с 0)
                                                     "endRowIndex": 1,  # до строки 4 НЕ включая
                                                     "startColumnIndex": start_col + 1,  # колонка A
                                                     "endColumnIndex": len(rows[2])# любые нужные колонки (A–T например)
                                                     },
                                           "bottom": {"style": "SOLID",
                                                      "width": 1,
                                                      "color": {"red": 0, "green": 0, "blue": 0}}}})

    #  Объединяем ячейки
    for idx in range(0, start_col):
        all_requests.append({
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 2,
                    "startColumnIndex": idx,
                    "endColumnIndex": idx + 1
                },
                "mergeType": "MERGE_ALL"}})

    current_month = date_objs[0].month
    group_start_col = start_col + 1  # 1-based

    month_starts = [group_start_col]  # Список колонок начала месяцев (первая всегда)

    for i, d in enumerate(date_objs[1:], start=1):
        if d.month != current_month:
            end_col_excl = start_col + i
            all_requests.append({
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": group_start_col - 1,
                        "endColumnIndex": end_col_excl
                    },
                    "mergeType": "MERGE_ALL"}})
            current_month = d.month
            group_start_col = end_col_excl + 1
            month_starts.append(group_start_col)

        elif i == len(date_objs[1:]):
            all_requests.append({
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": group_start_col - 1,
                        "endColumnIndex": start_col + 1 + i
                    },
                    "mergeType": "MERGE_ALL"}})

    for col_start in month_starts:
        col_index = col_start - 1
        all_requests.append({
            "updateBorders": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": len(rows),  # высота по вашим данным
                    "startColumnIndex": col_index,
                    "endColumnIndex": len(rows[1])
                },
                "left": {
                    "style": "SOLID",
                    "width": 1,
                    "color": {"red": 0, "green": 0, "blue": 0}}}})

    # Добавляем правила
    rules.clear()  # удалить ВСЕ правила
    rules.append(rule_blue)
    rules.append(rule_red)
    rules.append(rule_green)
    rules.append(rule_formula_monday)
    rules.save()
    # Добавляем форматирование
    spreadsheet.batch_update({"requests": all_requests})


def main_fbs_stocks(retries: int = 6) -> None:
    try:
        db_conn = DbConnection()
        db_conn.start_db()
        # add_fbs_stocks(db_conn=db_conn)
        # plan_sale(db_conn)
        create_12_na_273(db_conn)
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            time.sleep(10)
            main_fbs_stocks(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    main_fbs_stocks()
