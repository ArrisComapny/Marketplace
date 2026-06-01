from typing import Optional

from pydantic import Field

from .base import BaseRequest


class PostingFBOListFilter(BaseRequest):
    """Фильтр для поиска отправлений."""
    since: str
    to: str
    status: Optional[list[str]] = []
    posting_number: Optional[list[str]] = []
    order_number: Optional[list[str]] = []


class PostingFBOListWith(BaseRequest):
    """Дополнительные поля, которые нужно добавить в ответ."""
    analytics_data: Optional[bool] = False
    financial_data: Optional[bool] = False
    legal_info: Optional[bool] = False


class PostingFBOListRequest(BaseRequest):
    """Возвращает информацию об отправлениях схемы FBO. Метод /v3/posting/fbo/list."""
    cursor: Optional[str] = ""
    filter: PostingFBOListFilter
    limit: Optional[int] = 100
    sort_dir: Optional[str] = "asc"
    translit: Optional[bool] = False
    with_field: PostingFBOListWith = Field(default_factory=PostingFBOListWith, serialization_alias='with')
