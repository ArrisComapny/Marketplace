from typing import Optional

from .base import BaseRequest


class SupplyDetailsRequest(BaseRequest):
    """Запрос деталей поставки."""
    isPreorderID: Optional[str] = 'false'
