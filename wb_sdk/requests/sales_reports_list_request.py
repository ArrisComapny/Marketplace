from typing import Optional

from .base import BaseRequest


class SalesReportsListRequest(BaseRequest):
    dateFrom: str
    dateTo: str
    period: Optional[str] = 'daily'
    limit: Optional[int] = 1000
    offset: Optional[int] = 0
