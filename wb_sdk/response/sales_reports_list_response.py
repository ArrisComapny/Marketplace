from typing import Optional

from .base import BaseResponse
from ..entities import SalesReportList


class SalesReportsListResponse(BaseResponse):
    result: Optional[list[SalesReportList]] = []
