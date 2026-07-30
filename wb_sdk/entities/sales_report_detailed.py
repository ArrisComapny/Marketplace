from datetime import datetime, date
from typing import Optional

from .base import BaseEntity


class SalesReportDetailed(BaseEntity):
    """Строка детализации отчёта реализации (finance-api).

    Поля названы как в JSON нового API (camelCase), в отличие от старого
    statistics-api v5, где имена в snake_case.
    """
    reportId: int = None
    dateFrom: date = None
    dateTo: date = None
    createDate: date = None
    currency: str = None
    reportType: int = None
    rrdId: int = None
    giId: int = None
    dlvPrc: float = None
    fixTariffDateFrom: Optional[str] = None
    fixTariffDateTo: Optional[str] = None
    subjectName: str = None
    nmId: int = None
    brandName: str = None
    vendorCode: str = None
    title: str = None
    techSize: str = None
    sku: str = None
    docTypeName: str = None
    quantity: int = None
    retailPrice: float = None
    retailAmount: float = None
    salePercent: float = None
    commissionPercent: float = None
    officeName: str = None
    sellerOperName: str = None
    orderDt: datetime = None
    saleDt: datetime = None
    rrDate: date = None
    shkId: int = None
    retailPriceWithDisc: float = None
    deliveryAmount: int = None
    returnAmount: int = None
    deliveryService: float = None
    giBoxTypeName: str = None
    productDiscountForReport: float = None
    sellerPromo: float = None
    spp: float = None
    kvwBase: float = None
    kvw: float = None
    supRatingUp: float = None
    isKgvpV2: float = None
    ppvzSalesCommission: float = None
    forPay: float = None
    ppvzReward: float = None
    acquiringFee: float = None
    acquiringPercent: float = None
    paymentProcessing: str = None
    acquiringBank: str = None
    vw: float = None
    vwNds: float = None
    ppvzOfficeName: str = None
    ppvzOfficeId: int = None
    ppvzSupplierName: str = None
    ppvzSupplierInn: str = None
    declarationNumber: str = None
    bonusTypeName: str = None
    stickerId: str = None
    country: str = None
    srvDbs: bool = None
    penalty: float = None
    additionalPayment: float = None
    rebillLogisticCost: float = None
    rebillLogisticOrg: str = None
    paidStorage: float = None
    deduction: float = None
    paidAcceptance: float = None
    orderId: int = None
    kiz: str = None
    isB2b: bool = None
    trbxId: str = None
    installmentCofinancingAmount: float = None
    wibesDiscountPercent: float = None
    cashbackAmount: float = None
    cashbackDiscount: float = None
    cashbackCommissionChange: float = None
    paymentSchedule: str = None
    deliveryMethod: str = None
    sellerPromoId: int = None
    sellerPromoDiscount: float = None
    loyaltyId: int = None
    loyaltyDiscount: float = None
    uuidPromocode: str = None
    salePricePromocodeDiscountPrc: float = None
    articleSubstitution: str = None
    salePriceAffiliatedDiscountPrc: float = None
    agencyVat: float = None
    salePriceWholesaleDiscountPrc: float = None
    b2bCustomerTin: str = None
    orderUid: str = None
    srid: str = None
