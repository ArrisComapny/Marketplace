from typing import Optional

from .base import BaseResponse
from ..entities import PostingFBOList


class PostingFBOListResponse(BaseResponse):
    """Информация об отправлениях схемы FBO. Метод /v3/posting/fbo/list."""
    postings: list[PostingFBOList] = []
    cursor: Optional[str] = None
    has_next: bool = False
