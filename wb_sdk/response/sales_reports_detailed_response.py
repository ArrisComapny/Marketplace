from typing import Optional

from .base import BaseResponse
from ..entities import SalesReportDetailed


class SalesReportsDetailedResponse(BaseResponse):
    result: Optional[list[SalesReportDetailed]] = []
