from typing import Optional
from pydantic import ConfigDict, Field

from sb_sdk.entities import BaseEntity
from .base import BaseRequest


class SuppliesQueryRequest(BaseRequest):
    """Запрос по поставкам."""
    limit: Optional[int] = 1000
    offset: Optional[int] = 0

class SuppliesDatesBodyRequest(BaseEntity):
    """Фильтр по датам."""
    model_config = ConfigDict(populate_by_name=True)

    from_field: str = Field(alias='from')
    till: str
    type_field: Optional[str] = 'createDate'

class SuppliesBodyRequest(BaseRequest):
    """Запрос по поставкам."""
    dates: list[SuppliesDatesBodyRequest]
    statusIDs: Optional[list[int]] = []
