from datetime import datetime
from typing import Optional

from .base import BaseEntity


class PostingFBOListMoneyValue(BaseEntity):
    """Денежное значение."""
    amount: str = None
    currency: str = None


class PostingFBOListAdditionalData(BaseEntity):
    """additional_data"""
    key: str = None
    value: str = None


class PostingFBOListLegalInfo(BaseEntity):
    """Данные о юридическом лице покупателя."""
    company_name: str = None
    inn: str = None
    kpp: str = None


class PostingFBOListAnalyticsData(BaseEntity):
    """Данные аналитики."""
    city: str = None
    delivery_type: str = None
    is_legal: bool = None
    is_premium: bool = None
    payment_type_group_name: str = None
    warehouse_id: int = None
    warehouse_name: str = None
    client_delivery_date_begin: Optional[datetime] = None
    client_delivery_date_end: Optional[datetime] = None


class PostingFBOListFinancialDataProductCommission(BaseEntity):
    """Комиссия за товар."""
    amount: float = None
    percent: float = None
    currency: str = None


class PostingFBOListFinancialDataProduct(BaseEntity):
    """Информация о товаре в заказе."""
    product_id: int = None
    commission: Optional[PostingFBOListFinancialDataProductCommission] = None
    payout: float = None
    price: float = None
    old_price: float = None
    total_discount_value: float = None
    total_discount_percent: float = None
    actions: list[str] = []


class PostingFBOListFinancialData(BaseEntity):
    """Финансовые данные."""
    products: list[PostingFBOListFinancialDataProduct] = []
    cluster_from: str = None
    cluster_to: str = None


class PostingFBOListProduct(BaseEntity):
    """Товар в отправлении."""
    sku: int = None
    name: str = None
    quantity: int = None
    offer_id: str = None
    price: Optional[PostingFBOListMoneyValue] = None
    digital_codes: list[str] = []
    is_marketplace_buyout: bool = None


class PostingFBOListCancellation(BaseEntity):
    """Информация об отмене."""
    cancel_reason: str = None
    cancellation_type: str = None
    cancellation_initiator: str = None


class PostingFBOList(BaseEntity):
    """Информация об отправлении."""
    order_id: int = None
    order_number: str = None
    posting_number: str = None
    status: str = None
    substatus: str = None
    cancel_reason_id: int = None
    created_at: Optional[datetime] = None
    in_process_at: Optional[datetime] = None
    legal_info: Optional[PostingFBOListLegalInfo] = None
    products: list[PostingFBOListProduct] = []
    analytics_data: Optional[PostingFBOListAnalyticsData] = None
    financial_data: Optional[PostingFBOListFinancialData] = None
    cancellation: Optional[PostingFBOListCancellation] = None
    ext_type: str = None
    platform_name: str = None
    additional_data: list[PostingFBOListAdditionalData] = []
