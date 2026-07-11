from typing import Optional

from .base import BaseResponse
from ..entities import StocksReportWbWarehousesData


class StocksReportWbWarehousesResponse(BaseResponse):
    """Ответ метода остатков на складах WB."""
    data: Optional[StocksReportWbWarehousesData] = None
