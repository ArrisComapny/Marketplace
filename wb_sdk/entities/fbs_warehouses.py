from pydantic import Field

from .base import BaseEntity


class FBSWarehouses(BaseEntity):
    """Склад FBS."""
    name: str = None
    officeId: int = None
    id_field: int = Field(default=None, alias='id')
    cargoType: int = None
    deliveryType: int = None
    isDeleting: bool = None
    isProcessing: bool = None
