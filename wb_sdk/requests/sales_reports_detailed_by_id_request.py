from typing import Optional

from .base import BaseRequest


class SalesReportsDetailedByIdRequest(BaseRequest):
    limit: Optional[int] = 100000
    rrdId: Optional[int] = 0
