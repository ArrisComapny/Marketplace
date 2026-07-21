import os
import asyncio
import logging
import requests
import warnings
import nest_asyncio
import pandas as pd

from typing import Union
from datetime import datetime, timedelta, date
from sqlalchemy.exc import OperationalError

from ya_sdk.ya_api import YandexApi
from database import YaDbConnection
from data_classes import DataYaReport, DataYaCampaigns


nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

warnings.simplefilter(action='ignore', category=UserWarning)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def download_file(url: str, file_name: str) -> Union[str, None]:
    try:
        response = requests.get(url)
        response.raise_for_status()

        save_path = os.path.join(PROJECT_ROOT, 'templates', 'yandex_report', f'{file_name}.xlsx')

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


async def get_campaign_ids(api_key: str) -> list[DataYaCampaigns]:
    list_campaigns = []
    api_user = YandexApi(api_key=api_key)
    answer = await api_user.get_campaigns()
    if answer:
        for campaign in answer.campaigns:
            list_campaigns.append(DataYaCampaigns(client_id=str(campaign.business.field_id),
                                                  campaign_id=str(campaign.field_id),
                                                  name=campaign.domain,
                                                  placement_type=campaign.placementType))
    return list_campaigns


async def report_generate(client_id: str, api_key: str, campaigns: list[DataYaCampaigns],
                          date_now: date) -> Union[str, None]:
    date_from = date_now - timedelta(days=10)
    date_to = date_now - timedelta(days=1)

    report_id = None
    link_report = None
    substatus = {'NO_DATA': 'Для такого отчета нет данных.',
                 'TOO_LARGE': 'Отчет превысил допустимый размер — укажите меньший период времени '
                              'или уточните условия запроса.',
                 'RESOURCE_NOT_FOUND': 'Для такого отчета не удалось найти часть сущностей.'}
    api_user = YandexApi(api_key=api_key)
    campaign_ids = [int(campaign.campaign_id) for campaign in campaigns]
    answer = await api_user.get_reports_united_marketplace_services_generate(business_id=int(client_id),
                                                                             campaign_ids=campaign_ids,
                                                                             date_from=date_from.isoformat(),
                                                                             date_to=date_to.isoformat())
    if answer:
        if answer.result:
            report_id = answer.result.reportId
            logger.info(f"Запрос отправлен: {report_id}")

    if report_id is not None:
        retry = 3
        retry_pending = 10
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
                    elif answer_report_info.result.status == 'PENDING':
                        retry_pending -= 1
                        if not retry_pending:
                            logger.error(f"Ошибка формирования отчёта: долгий PENDING")
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


async def add_yandex_report_entry(path_file: str, campaigns: list[DataYaCampaigns]) -> Union[list[DataYaReport], None]:
    name_campaigns = {campaign.name: campaign.campaign_id for campaign in campaigns}
    headers_dict = {
        'client_id': {'ID бизнес-аккаунта': None},
        'campaign_name': {'Названия магазинов': None},
        'posting_number': {'Номер заказа или отгрузки': None},
        'operation_date': {'Дата оказания услуги': None,
                           'Дата и время оказания услуги': None},
        'service': {'Услуга': None},
        'vendor_code': {'Ваш SKU': None},
        'cost': {'Стоимость услуги (': None,
                 'Стоимость услуги, ₽': None,
                 'Стоимость услуги': None,
                 'Постоплата, ₽': None,
                 'Стоимость платного хранения, ₽': None}
    }
    headers = [key for val in headers_dict.values() for key in val.keys()]

    name_sheets = [
        'Обработка заказов в СЦ или ПВЗ',
        'Размещение товаров на витрине',
        'Обработка заказов на складе',
        'Приём платежа',
        'Перевод платежа',
        'Доставка покупателю',
        'Экспресс-доставка покупателю',
        'Поставка через транзитный склад',  # new
        'Доставка из-за рубежа',  # new pass
        'Программа лояльности и отзывы',
        'Буст продаж, оплата за показы',
        'Буст продаж, оплата за продажи',
        'Полки',
        'Баннеры',  # new pass
        'Хранение невыкупов и возвратов',
        'Рассрочка',  # new pass
        'Приём излишков на складе',  # new pass
        'Организация утилизации',
        'Вывоз со склада, СЦ, ПВЗ',
        'Организация забора заказов',  # new pass
        'Вознаграждение за продажу',  # new pass
        'Расширенный доступ к сервисам',  # new pass
        'Складская обработка',  # new
        'Персональный менеджер',
        'Доставка (средняя миля)',
        'Товарные баннеры',
        'Размещение товаров и услуг'
    ]

    try:
        excel_file = pd.ExcelFile(path_file)
        logger.info(f'Файл {path_file} прочитан успешно.')

        sheet_names = excel_file.sheet_names
        for s in sheet_names:
            if 'Платное хранение' in s:
                name_sheets.append(s)

        new_sheet_names = [s for s in sheet_names if s not in name_sheets + ['Сводка']]

        if new_sheet_names:
            logger.error(f'Появились новые листы: {", ".join(new_sheet_names)}')

        result_data = []

        for sheet in name_sheets:
            if sheet in sheet_names:
                df = pd.read_excel(path_file, sheet_name=sheet, header=None)

                header_row = 0
                for i, row in df.iterrows():
                    if any(cell in headers for cell in row if pd.notna(cell)):
                        header_row = i
                        break

                if header_row:
                    df = pd.read_excel(path_file, sheet_name=sheet, header=header_row)
                    df = df.fillna('')

                    for idx, row in df.iterrows():
                        try:
                            row_data = {}
                            for metric, value in headers_dict.items():
                                row_data[metric] = {}
                                for header in value.keys():
                                    if header in df.columns:
                                        if ('Буст продаж' in sheet or sheet == 'Полки') and header == 'Стоимость услуги, ₽':
                                            spp = row.get('Скидка за участие в совместных акциях', 0)
                                            spp = float(spp) if isinstance(spp, (float, int)) else 0
                                            row_data[metric][header] = float(row[header]) + spp
                                        elif sheet == 'Доставка (средняя миля)' and header == 'Стоимость услуги, ₽':
                                            spp = row.get('Скидка за участие в совместных акциях', 0)
                                            spp = -float(spp) if isinstance(spp, (float, int)) else 0
                                            row_data[metric][header] = float(row[header]) + spp
                                        else:
                                            row_data[metric][header] = row[header]
                                    else:
                                        if header == 'Стоимость услуги (':
                                            for column in df.columns:
                                                if header in column:
                                                    disc_loyalty = row['Unnamed: 47']
                                                    disc_joint = row['Unnamed: 48']
                                                    disc_loyalty = float(disc_loyalty) if isinstance(disc_loyalty,
                                                                                                     (float,
                                                                                                      int)) else 0
                                                    disc_joint = float(disc_joint) if isinstance(disc_joint,
                                                                                                 (float, int)) else 0
                                                    row_data[metric][header] = float(
                                                        row[column]) + disc_loyalty + disc_joint

                            client_id = convert_id(
                                next((v for v in row_data.get('client_id', {}).values() if v is not None), None))
                            campaign_name = next(
                                (v for v in row_data.get('campaign_name', {}).values() if v is not None), None)
                            posting_number = convert_id(
                                next((v for v in row_data.get('posting_number', {}).values() if v is not None), None))
                            operation_date = next(
                                (v for v in row_data.get('operation_date', {}).values() if v is not None), None)
                            cost = next((v for v in row_data.get('cost', {}).values() if v is not None), None)
                            service = next((v for v in row_data.get('service', {}).values() if v is not None), None)
                            vendor_code = next((v for v in row_data.get('vendor_code', {}).values() if v is not None),
                                               None)

                            if 'Платное хранение' in sheet:
                                operation_type = 'Платное хранение'
                            elif 'Размещение товаров и услуг' in sheet:
                                operation_type = 'Размещение товаров на витрине'
                            else:
                                operation_type = sheet

                            operation_date = datetime.strptime(operation_date, '%Y-%m-%d %H:%M:%S').date()
                            cost = round(float(cost), 2)

                            entry = DataYaReport(client_id=client_id,
                                                 campaign_id=name_campaigns.get(campaign_name, None),
                                                 date=operation_date,
                                                 posting_number=posting_number,
                                                 operation_type=operation_type,
                                                 vendor_code=vendor_code,
                                                 service=service,
                                                 cost=cost)
                            result_data.append(entry)
                        except Exception as e:
                            if sheet in ('Размещение товаров на витрине', 'Размещение товаров и услуг') and isinstance(idx, int) and int(idx) < 2:
                                continue
                            logger.error(f'Ошибка при чтении листа {sheet} строки {idx}: {e}')
            else:
                logger.info(f'Лист "{sheet}" не найден в файле.')

        aggregate = {}
        for row in result_data:
            key = (
                row.client_id,
                row.campaign_id,
                row.date,
                row.posting_number,
                row.operation_type,
                row.vendor_code,
                row.service
            )
            if key in aggregate:
                aggregate[key] += row.cost
            else:
                aggregate[key] = row.cost
        result_data = []
        for key, cost in aggregate.items():
            client_id, campaign_id, operation_date, posting_number, operation_type, vendor_code, service = key
            result_data.append(DataYaReport(client_id=client_id,
                                            campaign_id=campaign_id,
                                            date=operation_date,
                                            posting_number=posting_number,
                                            operation_type=operation_type,
                                            vendor_code=vendor_code,
                                            service=service,
                                            cost=cost))
        logger.info(f'Количество записей: {len(result_data)}')
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

        api_key_set = {client.api_key for client in clients}

        for api_key in api_key_set:
            list_campaigns = await get_campaign_ids(api_key=api_key)
            db_conn.add_ya_campaigns(list_campaigns=list_campaigns)

            client_dict = {}
            for campaign in list_campaigns:
                client_dict.setdefault(campaign.client_id, [])
                client_dict[campaign.client_id].append(campaign)

            date_now = date.today()

            for client_id, campaigns in client_dict.items():

                client = db_conn.get_client(client_id=client_id)

                logger.info(f"За дату {date_now - timedelta(days=1)}")
                logger.info(f"Добавление в базу данных компании '{client.name_company}'")
                path_file = await report_generate(client_id=client_id,
                                                  campaigns=campaigns,
                                                  api_key=client.api_key,
                                                  date_now=date_now)
                if path_file is not None:
                    list_reports = await add_yandex_report_entry(path_file=path_file, campaigns=campaigns)
                    db_conn.add_ya_report(list_reports=list_reports)
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
