from .base import BaseRequest


class FBSOrdersStatusRequest(BaseRequest):
    """Получить информацию о статусах сборочных заданий FBS."""
    orders: list[int]
