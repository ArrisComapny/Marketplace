from typing import Optional

from .base import BaseEntity


class Supplies(BaseEntity):
    """Информация о поставках."""
    phone: str
    supplyID: Optional[int] = None
    preorderID: Optional[int] = None
    createDate: str
    supplyDate: Optional[str] = None
    factDate: Optional[str] = None
    updatedDate: Optional[str] = None
    statusID: int
    boxTypeID: Optional[int] = None
    isBoxOnPallet: Optional[bool] = None
