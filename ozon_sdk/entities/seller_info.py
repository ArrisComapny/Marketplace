from typing import Optional

from .base import BaseEntity


class SellerInfoCompany(BaseEntity):
    """Компания продавца."""
    country: Optional[str] = None
    currency: Optional[str] = None
    inn: Optional[str] = None
    legal_name: Optional[str] = None
    name: Optional[str] = None
    ogrn: Optional[str] = None
    ownership_form: Optional[str] = None
    tax_system: Optional[str] = None


class SellerInfoRatingStatus(BaseEntity):
    """Статус значения рейтинга."""
    danger: Optional[bool] = None
    premium: Optional[bool] = None
    warning: Optional[bool] = None


class SellerInfoRatingValue(BaseEntity):
    """Значение рейтинга за период."""
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    formatted: Optional[str] = None
    status: Optional[SellerInfoRatingStatus] = None
    value: Optional[float] = None


class SellerInfoRating(BaseEntity):
    """Рейтинг продавца."""
    current_value: Optional[SellerInfoRatingValue] = None
    past_value: Optional[SellerInfoRatingValue] = None
    name: Optional[str] = None
    rating: Optional[str] = None
    status: Optional[str] = None
    value_type: Optional[str] = None


class SellerInfoSubscription(BaseEntity):
    """Подписка кабинета (Premium)."""
    is_premium: Optional[bool] = False
    type: Optional[str] = None
