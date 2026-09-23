from typing import Optional

from .base import BaseResponse
from ..entities import SellerInfoCompany, SellerInfoRating, SellerInfoSubscription


class SellerInfoResponse(BaseResponse):
    """Информация о кабинете продавца: компания, рейтинги, подписка."""
    company: Optional[SellerInfoCompany] = None
    ratings: Optional[list[SellerInfoRating]] = []
    subscription: Optional[SellerInfoSubscription] = None
