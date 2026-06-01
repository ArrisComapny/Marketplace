import datetime

from dataclasses import dataclass
from typing import Optional


@dataclass
class DataOzProductCard:
    sku: str
    vendor_code: str
    client_id: str
    brand: str
    category: str
    link: str
    price: float
    discount_price: float
    created_at: Optional[datetime.date] = None


@dataclass
class DataOzStatisticCardProduct:
    sku: str
    date: datetime.date
    add_to_cart_from_search_count: int
    add_to_cart_from_card_count: int
    view_search: int
    view_card: int
    orders_count: int
    orders_sum: float
    delivered_count: int
    returns_count: int
    cancel_count: int


@dataclass
class DataOzAdvert:
    id_advert: str
    field_type: str
    field_status: str
    name_advert: str
    create_time: datetime.date
    change_time: datetime.date
    start_time: datetime.date
    end_time: datetime.date


@dataclass
class DataOzStatisticAdvert:
    client_id: str
    date: datetime.date
    sku: str
    advert_id: str
    views: int
    clicks: int
    sum_cost: float
    orders_count: int
    sum_price: float


@dataclass
class DataOzStorage:
    date: datetime.date
    sku: str
    cost: float


@dataclass
class DataOzService:
    client_id: str
    date: datetime.date
    operation_type: str
    operation_type_name: str
    vendor_code: Optional[str]
    sku: str
    posting_number: str
    service: Optional[str]
    cost: float


@dataclass
class DataOzAdvertDailyBudget:
    advert_id: str
    daily_budget: float


@dataclass
class DataOzOrder:
    order_date: datetime.date
    client_id: str
    sku: str
    vendor_code: str
    posting_number: str
    delivery_schema: str
    quantities: int
    price: float
    status: str


@dataclass
class DataOzStock:
    date: datetime.date
    client_id: str
    sku: str
    vendor_code: str
    size: str
    quantity: int
    reserved: int


@dataclass
class DataOzBonus:
    date: datetime.date
    client_id: str
    sku: str
    vendor_code: str
    bonus: float
    amount: float
    bank_coinvestment: float
