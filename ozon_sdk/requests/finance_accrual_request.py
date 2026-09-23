from typing import Optional

from .base import BaseRequest


class FinanceAccrualByDayRequest(BaseRequest):
    """Начисления за день."""
    date: str
    last_id: Optional[str] = ''


class FinanceAccrualTypesRequest(BaseRequest):
    """Справочник начислений (тело запроса пустое)."""
    pass


class FinanceAccrualPostingsRequest(BaseRequest):
    """Начисления по отправлениям (до 200 номеров)."""
    posting_numbers: list[str]
