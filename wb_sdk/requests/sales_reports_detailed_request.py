from typing import Optional

from .base import BaseRequest


class SalesReportsDetailedRequest(BaseRequest):
    dateFrom: str
    dateTo: str
    limit: Optional[int] = 100000
    rrdId: Optional[int] = 0
    period: Optional[str] = 'weekly'
    fields: Optional[list[str]] = None

    def dict(self, **kwargs):
        # fields не передаём вовсе, если список не задан — API тогда вернёт все поля
        kwargs.setdefault('exclude_none', True)
        return super().dict(**kwargs)
