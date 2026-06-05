import os
import asyncio
import requests
import warnings

import logging
import nest_asyncio
import pandas as pd

from collections import defaultdict
from datetime import timedelta, date
from sqlalchemy.exc import OperationalError

from ya_sdk.ya_api import YandexApi
from database import YaDbConnection
from data_classes import DataYaReportShows, DataYaAdvertCost

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

warnings.simplefilter(action='ignore', category=UserWarning)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def download_file(url, file_name) -> str or None:
    try:
        response = requests.get(url)
        response.raise_for_status()

        save_path = os.path.join(PROJECT_ROOT, 'templates', 'yandex_report_shows', f'{file_name}.xlsx')

        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        with open(save_path, 'wb') as file:
            file.write(response.content)
        logger.info(f'Файл сохранен по пути: {save_path}')
        return save_path
    except requests.exceptions.RequestException as e:
        logger.error(f'Ошибка при скачивании файла: {e}')
        return None
    except Exception as e:
        logger.error(f'Неожиданная ошибка: {e}')
        return None


def convert_id(number):
    if number is not None:
        number = str(number).split('.')[0]
    return number


async def report_generate(client_id: str, api_key: str, date_now: date) -> str or None:
    date_from = date_now - timedelta(days=1)
    date_to = date_now - timedelta(days=1)

    report_id = None
    link_report = None
    substatus = {'NO_DATA': 'Для такого отчета нет данных.',
                 'TOO_LARGE': 'Отчет превысил допустимый размер — укажите меньший период времени '
                              'или уточните условия запроса.',
                 'RESOURCE_NOT_FOUND': 'Для такого отчета не удалось найти часть сущностей.'}
    api_user = YandexApi(api_key=api_key)
    answer = await api_user.get_reports_shows_boost_generate(business_id=int(client_id),
                                                             attribution_type="SHOWS",
                                                             date_from=date_from.isoformat(),
                                                             date_to=date_to.isoformat())
    if answer:
        if answer.result:
            report_id = answer.result.reportId
            logger.info(f"Запрос отправлен: {report_id}")

    if report_id is not None:
        retry = 3
        while True:
            await asyncio.sleep(10)
            answer_report_info = await api_user.get_reports_info(report_id=report_id)
            if answer_report_info:
                if answer_report_info.result:
                    if answer_report_info.result.status == 'DONE':
                        link_report = answer_report_info.result.file
                        if link_report is not None:
                            logger.info(f"Отчёт: {link_report}")
                        else:
                            logger.info(f"{substatus.get(answer_report_info.result.subStatus, None)}")
                        break
                    elif answer_report_info.result.status == 'FAILED':
                        logger.error(f"Ошибка формирования отчёта: FAILED")
                        break
                else:
                    retry -= 1
                    if not retry:
                        logger.error(f"Ошибка формирования отчёта: пустой result")
                        break
            else:
                retry -= 1
                if not retry:
                    logger.error(f"Ошибка формирования отчёта: пустой answer_report_info")
                    break
    else:
        logger.error(f"Не получилось отправить запрос")

    if link_report is not None:
        path_file = download_file(url=link_report, file_name=f'{client_id}_{date_to}')
        return path_file
    else:
        return None


async def add_yandex_report_entry(path_file: str, client_id: str, from_date: date) -> list[DataYaReportShows]:
    headers_dict = {'vendor_code': {'Ваш SKU': None},
                    'name_product': {'Название товара': None},
                    'shows': {'Показы товаров с бустом продаж с оплатой за показы': None},
                    'clicks': {'Клики по товарам с бустом продаж с оплатой за показы': None},
                    'add_to_card': {'Добавления в корзину с бустом продаж с оплатой за показы': None},
                    'orders_count': {'Заказанные товары с бустом продаж с оплатой за показы': None},
                    'cpm': {'CPM': None},
                    'cost': {'Расчётные расходы на буст продаж с оплатой за показы, ₽': None},
                    'orders_sum': {'Выручка с бустом продаж с оплатой за показы': None},
                    'advert_id': {'ID кампаний': None,
                                  'ID кампаний ': None},
                    'name_advert': {'Названия кампаний': None}}
    headers = [key for val in headers_dict.values() for key in val.keys()]

    name_sheets = ['Отчёт по товарам']

    try:
        excel_file = pd.ExcelFile(path_file)
        logger.info(f'Файл {path_file} прочитан успешно.')

        sheet_names = excel_file.sheet_names

        result_data = []

        for sheet in name_sheets:
            if sheet in sheet_names:
                df = pd.read_excel(path_file, sheet_name=sheet, header=None)

                header_row = 0
                for i, row in df.iterrows():
                    if any(cell in headers for cell in row if pd.notna(cell)):
                        header_row = i
                        break

                df = pd.read_excel(path_file, sheet_name=sheet, header=header_row)
                df = df.fillna('')

                for idx, row in df.iterrows():
                    try:
                        row_data = {}
                        for metric, value in headers_dict.items():
                            row_data[metric] = {}
                            for header in value.keys():
                                if header in df.columns:
                                    row_data[metric][header] = row[header]

                        vendor_code = next((v for v in row_data.get('vendor_code', {}).values() if v is not None), None)
                        name_product = next((v for v in row_data.get('name_product', {}).values() if v is not None),
                                            None)
                        shows = next((v for v in row_data.get('shows', {}).values() if v is not None), None)
                        clicks = next((v for v in row_data.get('clicks', {}).values() if v is not None), None)
                        add_to_card = next((v for v in row_data.get('add_to_card', {}).values() if v is not None), None)
                        orders_count = next((v for v in row_data.get('orders_count', {}).values() if v is not None),
                                            None)
                        cpm = next((v for v in row_data.get('cpm', {}).values() if v is not None), None)
                        cost = next((v for v in row_data.get('cost', {}).values() if v is not None), None)
                        orders_sum = next((v for v in row_data.get('orders_sum', {}).values() if v is not None), None)
                        advert_id = next((v for v in row_data.get('advert_id', {}).values() if v is not None), None)
                        name_advert = next((v for v in row_data.get('name_advert', {}).values() if v is not None), None)

                        shows = int(shows)
                        clicks = int(clicks)
                        add_to_card = int(add_to_card)
                        orders_count = int(orders_count)
                        cpm = round(float(cpm), 2)
                        cost = round(float(cost), 2)
                        orders_sum = round(float(orders_sum), 2)

                        entry = DataYaReportShows(client_id=client_id,
                                                  date=from_date,
                                                  vendor_code=vendor_code,
                                                  name_product=name_product,
                                                  shows=shows,
                                                  clicks=clicks,
                                                  add_to_card=add_to_card,
                                                  orders_count=orders_count,
                                                  cpm=cpm,
                                                  cost=cost,
                                                  orders_sum=orders_sum,
                                                  advert_id=advert_id,
                                                  name_advert=name_advert)
                        result_data.append(entry)
                    except Exception as e:
                        logger.error(f'Ошибка при чтении листа {sheet} строки {idx}: {e}')
            else:
                logger.error(f'Лист "{sheet}" не найден в файле.')

        aggregated = defaultdict(list)

        for stat in result_data:
            key = (
                stat.client_id,
                stat.date,
                stat.vendor_code,
                stat.name_product,
                stat.advert_id,
                stat.name_advert
            )
            aggregated[key].append(stat)

        # Собираем агрегированные результаты
        result_data = []

        for key, group in aggregated.items():
            client_id, date_field, vendor_code, name_product, advert_id, name_advert = key

            shows = sum(item.shows for item in group)
            clicks = sum(item.clicks for item in group)
            add_to_card = round(sum(item.add_to_card for item in group), 2)
            orders_count = sum(item.orders_count for item in group)
            cost = sum(item.cost for item in group)
            orders_sum = sum(item.orders_sum for item in group)

            cpm = round((cost / shows) * 1000, 2) if shows else 0

            result_data.append(DataYaReportShows(
                client_id=client_id,
                date=date_field,
                vendor_code=vendor_code,
                name_product=name_product,
                shows=shows,
                clicks=clicks,
                add_to_card=add_to_card,
                orders_count=orders_count,
                cpm=cpm,
                cost=round(cost, 2),
                orders_sum=round(orders_sum, 2),
                advert_id=advert_id,
                name_advert=name_advert
            ))

        logger.info(f'Количество записей по показам: {len(result_data)}')
        return result_data
    except Exception as e:
        logger.error(f'Ошибка при чтении файла {path_file}: {e}')


async def add_yandex_report_advert_entry(path_file: str, client_id: str, from_date: date) -> list[DataYaAdvertCost]:
    headers_dict = {'advert_id': {'ID кампании': None},
                    'name_advert': {'Название кампании': None},
                    'cost': {'Фактические расходы, ₽': None},
                    'bonus_deducted': {'Списано бонусов': None}}
    headers = [key for val in headers_dict.values() for key in val.keys()]

    name_sheets = ['Отчёт по кампаниям']

    try:
        excel_file = pd.ExcelFile(path_file)
        logger.info(f'Файл {path_file} прочитан успешно.')

        sheet_names = excel_file.sheet_names

        result_data = []

        for sheet in name_sheets:
            if sheet in sheet_names:
                df = pd.read_excel(path_file, sheet_name=sheet, header=None)

                header_row = 0
                for i, row in df.iterrows():
                    if any(cell in headers for cell in row if pd.notna(cell)):
                        header_row = i
                        break

                df = pd.read_excel(path_file, sheet_name=sheet, header=header_row)
                df = df.fillna('')

                for idx, row in df.iterrows():
                    try:
                        row_data = {}
                        for metric, value in headers_dict.items():
                            row_data[metric] = {}
                            for header in value.keys():
                                if header in df.columns:
                                    row_data[metric][header] = row[header]

                        advert_id = next((v for v in row_data.get('advert_id', {}).values() if v is not None), None)
                        name_advert = next((v for v in row_data.get('name_advert', {}).values() if v is not None), None)
                        cost = next((v for v in row_data.get('cost', {}).values() if v is not None), None)
                        bonus_deducted = next((v for v in row_data.get('bonus_deducted', {}).values() if v is not None),
                                              None)

                        cost = round(float(cost), 2)
                        bonus_deducted = round(float(bonus_deducted), 2)

                        entry = DataYaAdvertCost(client_id=client_id,
                                                 date=from_date,
                                                 advert_id=advert_id,
                                                 name_advert=name_advert,
                                                 cost=cost,
                                                 bonus_deducted=bonus_deducted)

                        result_data.append(entry)
                    except Exception as e:
                        logger.error(f'Ошибка при чтении листа {sheet} строки {idx}: {e}')
            else:
                logger.error(f'Лист "{sheet}" не найден в файле.')

        aggregated = defaultdict(list)

        for stat in result_data:
            key = (
                stat.client_id,
                stat.date,
                stat.advert_id,
                stat.name_advert
            )
            aggregated[key].append(stat)

        # Собираем агрегированные результаты
        result_data = []

        for key, group in aggregated.items():
            client_id, date_field, advert_id, name_advert = key

            cost = sum(item.cost for item in group)
            bonus_deducted = sum(item.bonus_deducted for item in group)

            result_data.append(DataYaAdvertCost(
                client_id=client_id,
                date=date_field,
                advert_id=advert_id,
                name_advert=name_advert,
                type_advert='SHOWS',
                cost=round(cost, 2),
                bonus_deducted=round(bonus_deducted, 2)
            ))

        logger.info(f'Количество записей по компаниям: {len(result_data)}')
        return result_data
    except Exception as e:
        logger.error(f'Ошибка при чтении файла {path_file}: {e}')


async def main_yandex_report(retries: int = 6) -> None:
    """
        Основная функция для обновления записей в базе данных.

        Получает список клиентов из базы данных,
        затем для каждого клиента добавляет записи за вчерашний день в таблицу `ya_report`.
    """
    try:
        db_conn = YaDbConnection()
        db_conn.start_db()

        clients = db_conn.get_clients(marketplace='Yandex')

        date_now = date.today()

        logger.info(f"За дату {date_now - timedelta(days=1)}")
        for client in clients:
            logger.info(f"Добавление в базу данных компании '{client.name_company}'")
            path_file = await report_generate(client_id=client.client_id,
                                              api_key=client.api_key,
                                              date_now=date_now)
            if path_file is not None:
                list_reports = await add_yandex_report_entry(path_file=path_file,
                                                             client_id=client.client_id,
                                                             from_date=date_now - timedelta(days=1))
                db_conn.add_ya_report_shows(list_reports=list_reports)
                list_reports_advert_cost = await add_yandex_report_advert_entry(path_file=path_file,
                                                                                client_id=client.client_id,
                                                                                from_date=date_now - timedelta(days=1))
                db_conn.add_ya_report_advert_cost(list_reports=list_reports_advert_cost)
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_yandex_report(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_yandex_report())
    loop.stop()
