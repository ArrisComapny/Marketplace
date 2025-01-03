from datetime import datetime, date
from typing import Optional

from .base import BaseEntity


class SupplierReportDetailByPeriod(BaseEntity):
    realizationreport_id: int = None
    date_from: date = None
    date_to: date = None
    create_dt: date = None
    currency_name: str = None
    suppliercontract_code: Optional[str] = None
    rrd_id: int = None
    gi_id: int = None
    subject_name: str = None
    nm_id: int = None
    brand_name: str = None
    sa_name: str = None
    ts_name: str = None
    barcode: str = None
    doc_type_name: str = None
    quantity: int = None
    retail_price: float = None
    retail_amount: float = None
    sale_percent: int = None
    commission_percent: float = None
    office_name: str = None
    supplier_oper_name: str = None
    order_dt: datetime = None
    sale_dt: datetime = None
    rr_dt: date = None
    shk_id: int = None
    retail_price_withdisc_rub: float = None
    delivery_amount: int = None
    return_amount: int = None
    delivery_rub: float = None
    gi_box_type_name: str = None
    product_discount_for_report: float = None
    supplier_promo: float = None
    rid: int = None
    ppvz_spp_prc: float = None
    ppvz_kvw_prc_base: float = None
    ppvz_kvw_prc: float = None
    sup_rating_prc_up: float = None
    is_kgvp_v2: float = None
    ppvz_sales_commission: float = None
    ppvz_for_pay: float = None
    ppvz_reward: float = None
    acquiring_fee: float = None
    acquiring_bank: str = None
    ppvz_vw: float = None
    ppvz_vw_nds: float = None
    ppvz_office_id: int = None
    ppvz_office_name: str = None
    ppvz_supplier_id: int = None
    ppvz_supplier_name: str = None
    ppvz_inn: str = None
    declaration_number: str = None
    bonus_type_name: str = None
    sticker_id: str = None
    site_country: str = None
    penalty: float = None
    additional_payment: float = None
    rebill_logistic_cost: float = None
    rebill_logistic_org: str = None
    kiz: str = None
    storage_fee: float = None
    deduction: float = None
    acceptance: float = None
    srid: str = None
    report_type: int = None

