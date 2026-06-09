from typing import Optional

from .base import BaseResponse
from ..entities import Supplies


class SuppliesResponse(BaseResponse):
    """Список поставок."""
    result: Optional[list[Supplies]] = []
