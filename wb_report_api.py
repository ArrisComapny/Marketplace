import sys
import asyncio
import nest_asyncio
import logging

from datetime import datetime, timedelta, timezone, date
from sqlalchemy.exc import OperationalError

from wb_sdk.errors import ClientError
from wb_sdk.wb_api import WBApi
from wb_sdk.entities import SalesReportDetailed
from database import WBDbConnection
from data_classes import DataWBReport

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

# Лимит finance-api: 1 запрос в минуту на аккаунт продавца
THROTTLE_SECONDS = 61
LIST_LIMIT = 1000
DETAILED_LIMIT = 100000

MSK = timezone(timedelta(hours=3))


def to_msk_date(value: datetime) -> date:
    """API отдаёт время в UTC — переводим в московское, иначе даты
    ночных заказов (00:00-03:00 МСК) уезжают на день назад."""
    if value.tzinfo is not None:
        value = value.astimezone(MSK)
    return value.date()


def _f(value) -> float:
    return round(float(value or 0), 2)


def entity_to_data(row: SalesReportDetailed, operation_date: date) -> DataWBReport:
    """Строка finance-api -> DataWBReport (имена полей как в statistics-api v5).

    Неочевидные соответствия:
      - sku в БД = nmId из API (код номенклатуры), а barcode в БД = sku из API (баркод)
      - posting_number в БД = srid из API
      - ppvz_supplier_id: в finance-api отсутствует, пишем "0"
    """
    return DataWBReport(
        realizationreport_id=str(row.reportId),
        gi_id=str(row.giId or 0),
        subject_name=row.subjectName or "",
        sku=str(row.nmId or 0),
        brand=row.brandName or "",
        vendor_code=row.vendorCode or "",
        size=row.techSize or "",
        barcode=row.sku or "",
        doc_type_name=row.docTypeName or "",
        quantity=int(row.quantity or 0),
        retail_price=_f(row.retailPrice),
        retail_amount=_f(row.retailAmount),
        sale_percent=int(row.salePercent or 0),
        commission_percent=_f(row.commissionPercent),
        office_name=row.officeName or "",
        supplier_oper_name=row.sellerOperName or "",
        order_date=to_msk_date(row.orderDt),
        sale_date=to_msk_date(row.saleDt),
        operation_date=operation_date,
        shk_id=str(row.shkId or ""),
        retail_price_withdisc_rub=_f(row.retailPriceWithDisc),
        delivery_amount=int(row.deliveryAmount or 0),
        return_amount=int(row.returnAmount or 0),
        delivery_rub=_f(row.deliveryService),
        gi_box_type_name=row.giBoxTypeName or "",
        product_discount_for_report=_f(row.productDiscountForReport),
        supplier_promo=_f(row.sellerPromo),
        order_id=str(row.orderId or 0),
        ppvz_spp_prc=_f(row.spp),
        ppvz_kvw_prc_base=_f(row.kvwBase),
        ppvz_kvw_prc=_f(row.kvw),
        sup_rating_prc_up=_f(row.supRatingUp),
        is_kgvp_v2=_f(row.isKgvpV2),
        ppvz_sales_commission=_f(row.ppvzSalesCommission),
        ppvz_for_pay=_f(row.forPay),
        ppvz_reward=_f(row.ppvzReward),
        acquiring_fee=_f(row.acquiringFee),
        acquiring_bank=row.acquiringBank or "",
        ppvz_vw=_f(row.vw),
        ppvz_vw_nds=_f(row.vwNds),
        ppvz_office_id=str(row.ppvzOfficeId or 0),
        ppvz_office_name=row.ppvzOfficeName or "",
        ppvz_supplier_id="0",
        ppvz_supplier_name=row.ppvzSupplierName or "",
        ppvz_inn=row.ppvzSupplierInn or "",
        declaration_number=row.declarationNumber or "",
        bonus_type_name=row.bonusTypeName or None,
        sticker_id=str(row.stickerId or 0),
        site_country=row.country or "",
        penalty=_f(row.penalty),
        additional_payment=_f(row.additionalPayment),
        rebill_logistic_cost=_f(row.rebillLogisticCost),
        rebill_logistic_org=row.rebillLogisticOrg or None,
        kiz=row.kiz or None,
        storage_fee=_f(row.paidStorage),
        deduction=_f(row.deduction),
        acceptance=_f(row.paidAcceptance),
        posting_number=row.srid or "",
    )


async def get_report_daily(db_conn: WBDbConnection, client_id: str, name_company: str, api_key: str,
                           date_from: datetime, date_to: datetime) -> None:
    """
        Получает ежедневные детализированные отчёты из finance-api за период
        и сохраняет их в таблицу wb_report_daily.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            name_company (str): Название магазина (для логов).
            api_key (str): API KEY кабинета.
            date_from (datetime): Начальная дата периода.
            date_to (datetime): Конечная дата периода.
    """
    logger.info(f"Получение отчёта для {name_company} за период от {date_from.date().isoformat()} "
                f"до {date_to.date().isoformat()}")

    api_user = WBApi(api_key=api_key)

    first_request = True

    async def throttle():
        nonlocal first_request
        if first_request:
            first_request = False
        else:
            await asyncio.sleep(THROTTLE_SECONDS)

    # Список отчётов за период
    reports = []
    offset = 0
    while True:
        await throttle()
        answer = await api_user.get_sales_reports_list(date_from=date_from.strftime('%Y-%m-%dT%H:%M:%S'),
                                                       date_to=date_to.strftime('%Y-%m-%dT%H:%M:%S'),
                                                       period='daily',
                                                       limit=LIST_LIMIT,
                                                       offset=offset)
        if not answer.result:
            break
        reports.extend(answer.result)
        if len(answer.result) < LIST_LIMIT:
            break
        offset += LIST_LIMIT

    if not reports:
        logger.info(f"Нет ежедневных отчётов для {name_company} за период")
        return

    # Пропускаем уже загруженные отчёты
    existing_ids = set(db_conn.get_wb_report_daily_ids(client_id=client_id))
    new_reports = [r for r in reports if str(r.reportId) not in existing_ids]
    logger.info(f"Найдено отчётов для {name_company}: {len(reports)}, новых: {len(new_reports)}")

    for report in new_reports:
        # Детализация отчёта частями по rrdId
        rows = []
        rrd_id = 0
        while True:
            await throttle()
            answer = await api_user.get_sales_reports_detailed(report_id=report.reportId,
                                                               limit=DETAILED_LIMIT,
                                                               rrd_id=rrd_id)
            if not answer.result:
                break
            rows.extend(answer.result)
            rrd_id = answer.result[-1].rrdId
            if len(answer.result) < DETAILED_LIMIT:
                break

        # Дата формирования отчёта = дата операции (operation_date)
        list_report = [entity_to_data(row, operation_date=report.createDate) for row in rows]
        logger.info(f"Отчёт {report.reportId} за {report.dateFrom.isoformat()}, "
                    f"количество записей для {name_company}: {len(list_report)}")

        db_conn.add_wb_report_daily_entry(client_id=client_id,
                                          operation_date=report.createDate,
                                          realizationreport_id=str(report.reportId),
                                          list_report=list_report)


async def main_wb_report_api(retries: int = 6) -> None:
    try:
        db_conn = WBDbConnection()

        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="WB")

        # Необязательный фильтр по магазинам: python wb_report_api.py TiVi HuoGuo
        names = sys.argv[1:]
        if names:
            clients = [client for client in clients if client.name_company in names]
            logger.info(f"Фильтр по магазинам: {', '.join(names)} (кабинетов: {len(clients)})")

        date_now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        date_from = date_now - timedelta(days=15)
        date_to = date_now - timedelta(microseconds=1)

        async def run_client(client) -> None:
            try:
                await get_report_daily(db_conn=db_conn,
                                       client_id=client.client_id,
                                       name_company=client.name_company,
                                       api_key=client.api_key,
                                       date_from=date_from,
                                       date_to=date_to)
            except ClientError as e:
                logger.error(f"{client.name_company}: {e}")

        # Лимит запросов у finance-api на кабинет, поэтому кабинеты идут параллельно
        await asyncio.gather(*(run_client(client) for client in clients))
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_wb_report_api(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_wb_report_api())
    loop.stop()
