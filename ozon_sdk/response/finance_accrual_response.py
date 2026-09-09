from typing import Optional

from .base import BaseResponse
from ..entities import FinanceAccrual, FinanceAccrualType, FinanceAccrualPostingAccruals


class FinanceAccrualByDayResponse(BaseResponse):
    """Начисления за день."""
    accruals: list[FinanceAccrual] = []
    last_id: Optional[str] = None


class FinanceAccrualTypesResponse(BaseResponse):
    """Справочник начислений."""
    accrual_types: list[FinanceAccrualType] = []


class FinanceAccrualPostingsResponse(BaseResponse):
    """Начисления по отправлениям."""
    posting_accruals: list[FinanceAccrualPostingAccruals] = []
