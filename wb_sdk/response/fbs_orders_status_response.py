from .base import BaseResponse
from ..entities import FBSOrdersStatus


class FBSOrdersStatusResponse(BaseResponse):
    """Возвращает статус сборочных заданий FBS."""
    orders: list[FBSOrdersStatus] = []
