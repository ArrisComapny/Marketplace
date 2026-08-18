import datetime

from typing import Optional, Union
from dataclasses import dataclass


@dataclass
class DataOperation:
    client_id: str
    accrual_date: datetime.date
    type_of_transaction: str
    vendor_code: str
    delivery_schema: str
    posting_number: str
    sku: str
    sale: float
    quantities: int
    commission: Optional[float] = None
    bonus: Optional[float] = None


@dataclass
class DataCostPrice:
    month_date: int
    year_date: int
    vendor_code: str
    cost: float


@dataclass
class DataSelfPurchase:
    client_id: str
    order_date: datetime.date
    accrual_date: datetime.date
    vendor_code: str
    quantities: int
    price: float


@dataclass
class DataOrder:
    client: "Client"
    vendor_code: str
    orders_count: float


@dataclass
class DataStock:
    client: str
    vendor_code: str
    quantity: int


@dataclass
class DataProfit:
    marketplace: str
    client_id: str
    vendor_code: str
    sale: float
    cost: float
    commission: float
    acquiring: float
    logistics: float
    storage: float
    advertising: float
    other: float
    tac: float
    quantities: float
    profit: float


@dataclass
class DataRate:
    date: datetime.date
    currency: str
    rate: float


@dataclass
class DataOverseasPurchase:
    accrual_date: datetime.date
    vendor_code: str
    quantities: int
    price: float
    log_cost: float
    log_add_cost: float


@dataclass
class DataRating:
    query_id: int
    cpm: Optional[float] = None
    promo_position: Optional[int] = None
    position: Optional[int] = None
    advert_id: Optional[str] = None


@dataclass
class DataQuery:
    id_query: int
    query: str
    sku: str
    vendor_code: str
    entrepreneur: str


@dataclass
class DataCommodityAsset:
    date: datetime.date
    vendor_code: str
    fbs: int
    on_the_way: int


@dataclass
class DataSupply:
    date: datetime.date
    vendor_code: str
    supplies: int


@dataclass
class DataPlanSale:
    date: datetime.date
    vendor_code: str
    quantity_plan: int
    price_plan: float
    sum_price_plan: float
    profit_proc: float
    profit: float
    supplies: Union[int, str]

@dataclass
class DataInventory:
    id_inventory: str
    date: datetime.date
    vendor_code: str
    quantity: int

