from typing import Optional

from .base import BaseRequest


class StocksReportWbWarehousesRequest(BaseRequest):
    """Остатки на складах WB (новый метод analytics)."""
    limit: Optional[int] = 1000
    offset: Optional[int] = 0
