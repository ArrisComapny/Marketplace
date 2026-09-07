from typing import Optional

from .base import BaseResponse
from ..entities import SalesReportDetailed


class SalesReportsDetailedByPeriodResponse(BaseResponse):
    result: Optional[list[SalesReportDetailed]] = []
