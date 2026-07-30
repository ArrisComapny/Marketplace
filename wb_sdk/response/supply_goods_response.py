from typing import Optional

from .base import BaseResponse
from ..entities import SupplyGoods


class SupplyGoodsResponse(BaseResponse):
    """Товары поставки."""
    result: Optional[list[SupplyGoods]] = []
