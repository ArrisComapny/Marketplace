from typing import Optional

from .base import BaseEntity


class SupplyGoods(BaseEntity):
    """Товар поставки."""
    barcode: Optional[str] = None
    vendorCode: Optional[str] = None
    nmID: Optional[int] = None
    needKiz: Optional[bool] = None
    tnved: Optional[str] = None
    techSize: Optional[str] = None
    color: Optional[str] = None
    supplierBoxAmount: Optional[int] = None
    quantity: Optional[int] = None
    readyForSaleQuantity: Optional[int] = None
    unloadingQuantity: Optional[int] = None
    acceptedQuantity: Optional[int] = None
