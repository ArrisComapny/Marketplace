from pydantic import Field

from .base import BaseEntity

class FBSOrdersStatus(BaseEntity):
    """Статус сборочного задания FBS."""
    id_field: int = Field(default=None, alias='id')
    isCancellable: bool = None
    supplierStatus: str = None
    wbStatus: str = None

