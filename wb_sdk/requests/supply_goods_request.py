from typing import Optional

from .base import BaseRequest


class SupplyGoodsRequest(BaseRequest):
    """Запрос товаров поставки."""
    limit: Optional[int] = 1000
    offset: Optional[int] = 0
    isPreorderID: Optional[str] = 'false'
