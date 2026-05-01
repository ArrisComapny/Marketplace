from datetime import datetime
from typing import Optional

from .picking import Picking
from .base import BaseEntity


class PostingFBOGetAdditionalData(BaseEntity):
    """additional_data"""
    key: str = None
    value: str = None


class PostingFBOGetAnalyticsData(BaseEntity):
    """Данные аналитики."""
    city: str = None
    delivery_type: str = None
    is_legal: bool = None
    is_premium: bool = None
    payment_type_group_name: str = None
    warehouse_id: int = None
    warehouse_name: str = None


class PostingFBOGetFinancialDataProduct(BaseEntity):
    """Товар в заказе."""
    actions: list[str] = []
    commission_amount: float = None
    commission_percent: int = None
    commissions_currency_code: str = None
    old_price: float = None
    payout: float = None
    picking: Optional[Picking] = None
    price: float = None
    product_id: int = None
    quantity: int = None
    total_discount_percent: float = None
    total_discount_value: float = None
    customer_price: float = None


class PostingFBOGetFinancialData(BaseEntity):
    """Финансовые данные."""
    cluster_from: str = None
    cluster_to: str = None
    products: list[PostingFBOGetFinancialDataProduct] = []


class PostingFBOGetProduct(BaseEntity):
    """Товар в отправлении."""
    digital_codes: list[str] = []
    name: str = None
    offer_id: str = None
    currency_code: str = None
    price: str = None
    quantity: int = None
    sku: int = None


class PostingFBOGet(BaseEntity):
    """Информация об отправлении."""
    additional_data: list[PostingFBOGetAdditionalData] = []
    analytics_data: Optional[PostingFBOGetAnalyticsData] = None
    cancel_reason_id: int = None
    created_at: datetime = None
    financial_data: Optional[PostingFBOGetFinancialData] = None
    in_process_at: datetime = None
    order_id: int = None
    order_number: str = None
    posting_number: str = None
    products: list[PostingFBOGetProduct] = []
    status: str = None

