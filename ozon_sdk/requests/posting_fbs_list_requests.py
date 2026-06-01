from typing import Optional

from pydantic import Field

from .base import BaseRequest


class PostingFBSListFilterLastChangedStatusDate(BaseRequest):
    """Период, в который последний раз изменялся статус у отправлений."""
    from_field: Optional[str] = Field(default=None, serialization_alias='from')
    to: Optional[str] = None


class PostingFBSListFilter(BaseRequest):
    """Фильтр для поиска отправлений."""
    since: str
    to: str
    statuses: Optional[list[str]] = []
    order_id: Optional[int] = None
    order_numbers: Optional[list[str]] = []
    delivery_method_ids: Optional[list[int]] = []
    provider_ids: Optional[list[int]] = []
    warehouse_ids: Optional[list[int]] = []
    is_blr_traceable: Optional[bool] = None
    last_changed_status_date: Optional[PostingFBSListFilterLastChangedStatusDate] = None


class PostingFBSListWith(BaseRequest):
    """Дополнительные поля, которые нужно добавить в ответ."""
    analytics_data: Optional[bool] = False
    barcodes: Optional[bool] = False
    financial_data: Optional[bool] = False
    legal_info: Optional[bool] = False
    translit: Optional[bool] = False


class PostingFBSListRequest(BaseRequest):
    """Возвращает информацию об отправлениях схемы FBS. Метод /v4/posting/fbs/list."""
    cursor: Optional[str] = ""
    filter: PostingFBSListFilter
    limit: Optional[int] = 100
    sort_dir: Optional[str] = "asc"
    with_field: PostingFBSListWith = Field(default_factory=PostingFBSListWith, serialization_alias='with')
