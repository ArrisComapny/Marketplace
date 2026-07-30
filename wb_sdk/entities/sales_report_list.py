from datetime import date

from .base import BaseEntity


class SalesReportList(BaseEntity):
    """Отчёт реализации из списка отчётов (finance-api)."""
    reportId: int = None
    sellerFinanceName: str = None
    dateFrom: date = None
    dateTo: date = None
    createDate: date = None
    currency: str = None
    reportType: int = None
    retailAmountSum: float = None
    forPaySum: float = None
    avgSalePercent: float = None
    deliveryServiceSum: float = None
    paidStorageSum: float = None
    paidAcceptanceSum: float = None
    deductionSum: float = None
    penaltySum: float = None
    additionalPaymentSum: float = None
    cashbackAmountSum: float = None
    cashbackDiscountSum: float = None
    cashbackCommissionChangeSum: float = None
    paymentSchedule: str = None
    bankPaymentSum: float = None
