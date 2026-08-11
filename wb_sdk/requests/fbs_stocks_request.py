from .base import BaseRequest


class FBSStocksRequest(BaseRequest):
    """Получить информацию об остатках FBS."""
    chrtIds: list[int]
