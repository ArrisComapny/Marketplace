from typing import Optional

from .base import BaseResponse


class SupplyDetailsResponse(BaseResponse):
    """Детали поставки."""
    phone: Optional[str] = None
    statusID: int = None
    virtualTypeID: Optional[int] = None
    boxTypeID: Optional[int] = None
    createDate: Optional[str] = None
    supplyDate: Optional[str] = None
    factDate: Optional[str] = None
    updatedDate: Optional[str] = None
    warehouseID: Optional[int] = None
    warehouseName: Optional[str] = None
    actualWarehouseID: Optional[int] = None
    actualWarehouseName: Optional[str] = None
    transitWarehouseID: Optional[int] = None
    transitWarehouseName: Optional[str] = None
    acceptanceCost: Optional[float] = None
    paidAcceptanceCoefficient: Optional[float] = None
    rejectReason: Optional[str] = None
    supplierAssignName: Optional[str] = None
    storageCoef: Optional[str] = None
    deliveryCoef: Optional[str] = None
    quantity: Optional[int] = None
    readyForSaleQuantity: Optional[int] = None
    acceptedQuantity: Optional[int] = None
    unloadingQuantity: Optional[int] = None
    depersonalizedQuantity: Optional[int] = None
    isBoxOnPallet: Optional[bool] = None
