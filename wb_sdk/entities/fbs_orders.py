import datetime

from pydantic import Field
from typing import Any, Optional

from .base import BaseEntity


class FBSOrdersAddress(BaseEntity):
    """Детализованный адрес покупателя для доставки."""
    fullAddress: str = None
    longitude: float = None
    latitude: float = None


class FBSOrdersOptions(BaseEntity):
    """Опции заказа."""
    isB2b: bool = None


class FBSOrders(BaseEntity):
    """Информация о сборочном задании FBS."""
    address: Optional[FBSOrdersAddress] = None
    scanPrice: Optional[float] = None
    deliveryType: str = None
    supplyId: str = None
    orderUid: str = None
    article: str = None
    colorCode: str = None
    rid: str = None
    createdAt: datetime.datetime
    offices: list[str] = []
    skus: list[str] = []
    id_field: int = Field(default=None, alias='id')
    warehouseId: int = None
    officeId: int = None
    nmId: int = None
    chrtId: int = None
    price: int = None
    convertedPrice: int = None
    currencyCode: int = None
    convertedCurrencyCode: int = None
    cargoType: int = None
    crossBorderType: int = None
    comment: str = None
    isZeroOrder: bool = None
    options: FBSOrdersOptions = None
