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
# Страница 100000 строк с урезанными полями ≈ 130 МБ, ~1.5 мин загрузки (таймаут POST в движке 240 с)
LIMIT = 100000

# Запрашиваем только поля, которые пишем в таблицу (+ rrdId для пагинации) —
# без этого API отдаёт ~90 полей на строку и страница весит вдвое больше
REPORT_FIELDS = [
    'rrdId', 'reportId', 'giId', 'subjectName', 'nmId', 'brandName', 'vendorCode', 'techSize', 'sku',
    'docTypeName', 'quantity', 'retailPrice', 'retailAmount', 'salePercent', 'commissionPercent',
    'officeName', 'sellerOperName', 'orderDt', 'saleDt', 'rrDate', 'shkId', 'retailPriceWithDisc',
    'deliveryAmount', 'returnAmount', 'deliveryService', 'giBoxTypeName', 'productDiscountForReport',
    'sellerPromo', 'orderId', 'spp', 'kvwBase', 'kvw', 'supRatingUp', 'isKgvpV2', 'ppvzSalesCommission',
    'forPay', 'ppvzReward', 'acquiringFee', 'acquiringBank', 'vw', 'vwNds', 'ppvzOfficeId', 'ppvzOfficeName',
    'ppvzSupplierName', 'ppvzSupplierInn', 'declarationNumber', 'bonusTypeName', 'stickerId', 'country',
    'penalty', 'additionalPayment', 'rebillLogisticCost', 'rebillLogisticOrg', 'kiz', 'paidStorage',
    'deduction', 'paidAcceptance', 'srid',
]

MSK = timezone(timedelta(hours=3))


def to_msk_date(value: datetime) -> date:
    """API отдаёт время в UTC — переводим в московское, иначе даты
    ночных заказов (00:00-03:00 МСК) уезжают на день назад."""
    if value.tzinfo is not None:
        value = value.astimezone(MSK)
    return value.date()


def _f(value) -> float:
    return round(float(value or 0), 2)


def entity_to_data(row: SalesReportDetailed) -> DataWBReport:
    """Строка finance-api -> DataWBReport (имена полей как в statistics-api v5).

    Неочевидные соответствия:
      - sku в БД = nmId из API (артикул WB), а barcode в БД = sku из API (баркод)
      - order_id в БД = orderId из API (поле rid в finance-api отсутствует)
      - operation_date в БД = rrDate (в старом методе — rr_dt)
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
        operation_date=row.rrDate,
        shk_id=str(row.shkId or 0),
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


async def get_report(db_conn: WBDbConnection, client_id: str, api_key: str, date_from: datetime,
                     date_to: datetime) -> None:
    """
        Получает детализацию отчётов реализации по WB для указанного клиента за период
        через finance-api (POST /api/finance/v1/sales-reports/detailed) —
        замена отключаемого GET /api/v5/supplier/reportDetailByPeriod.

        Args:
            db_conn (WBDbConnection): Объект соединения с базой данных.
            client_id (str): ID кабинета.
            api_key (str): API KEY кабинета.
            date_from (datetime): Начальная дата периода.
            date_to (datetime): Конечная дата периода.
    """

    list_report = []
    rrd_id = 0

    # Инициализация API-клиента WB
    api_user = WBApi(api_key=api_key)
    while True:
        answer = await api_user.get_sales_reports_detailed_by_period(
            date_from=date_from.strftime('%Y-%m-%dT%H:%M:%S'),
            date_to=date_to.strftime('%Y-%m-%dT%H:%M:%S'),
            limit=LIMIT,
            rrd_id=rrd_id,
            fields=REPORT_FIELDS)

        # Пустой ответ (204) — конец выгрузки, а не ошибка
        if not answer.result:
            break

        list_report.extend(entity_to_data(row) for row in answer.result)
        rrd_id = answer.result[-1].rrdId

        if len(answer.result) < LIMIT:
            break
        await asyncio.sleep(THROTTLE_SECONDS)   # лимит WB: 1 запрос/мин

    # Пустой отчёт — не затираем уже записанный период
    if not list_report:
        logger.warning(f"Пустой отчёт по {client_id} — запись пропущена")
        return

    logger.info(f"Количество записей: {len(list_report)}")
    db_conn.add_wb_report_entry(client_id=client_id, start_date=date_from, list_report=list_report)


async def main_wb_report(retries: int = 6) -> None:
    try:
        db_conn = WBDbConnection()

        db_conn.start_db()

        clients = db_conn.get_clients(marketplace="WB")

        date_now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        date_from = date_now - timedelta(days=14)
        date_to = date_now - timedelta(microseconds=1)

        for client in clients:
            try:
                logger.info(f"Получение отчёта для {client.name_company} за период от {date_from.date().isoformat()} "
                            f"до {date_to.date().isoformat()}")
                await get_report(db_conn=db_conn,
                                 client_id=client.client_id,
                                 api_key=client.api_key,
                                 date_from=date_from,
                                 date_to=date_to)
            except ClientError as e:
                logger.error(f'{e}')
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            await asyncio.sleep(10)
            await main_wb_report(retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_wb_report())
    loop.stop()
