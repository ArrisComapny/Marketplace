from .base import BaseEntity


class StocksReportWbWarehousesItem(BaseEntity):
    """Строка остатков: товар × размер × склад."""
    nmId: int = None
    chrtId: int = None
    warehouseId: int = None
    warehouseName: str = None
    regionName: str = None
    quantity: int = None
    inWayToClient: int = None
    inWayFromClient: int = None


class StocksReportWbWarehousesData(BaseEntity):
    """Обёртка data с массивом строк остатков."""
    items: list[StocksReportWbWarehousesItem] = []
