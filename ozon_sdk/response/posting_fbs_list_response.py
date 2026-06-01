from typing import Optional

from .base import BaseResponse
from ..entities import PostingFBSListPosting


class PostingFBSListResponse(BaseResponse):
    """Информация об отправлениях схемы FBS. Метод /v4/posting/fbs/list."""
    postings: list[PostingFBSListPosting] = []
    cursor: Optional[str] = None
    has_next: bool = False
