from .base import BaseEntity


class FBSStocks(BaseEntity):
    """Остатки на складе FBS."""
    chrtId: int = None
    amount: int = None

