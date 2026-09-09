from typing import Optional

from .base import BaseEntity


class FinanceAccrualMoney(BaseEntity):
    """Сумма (строкой) и валюта."""
    amount: Optional[str] = None
    currency: Optional[str] = None


class FinanceAccrualFee(BaseEntity):
    """Начисление по типу из справочника /v1/finance/accrual/types."""
    type_id: Optional[int] = None
    accrued: Optional[FinanceAccrualMoney] = None


class FinanceAccrualItemFee(BaseEntity):
    """Начисления по товару (SKU)."""
    sku: Optional[int] = None
    fees: list[FinanceAccrualFee] = []


class FinanceAccrualItemFees(BaseEntity):
    fees: list[FinanceAccrualItemFee] = []


class FinanceAccrualContainerFees(BaseEntity):
    fees: list[FinanceAccrualFee] = []


class FinanceAccrualProductCommission(BaseEntity):
    """Продажа/возврат товара: цена, комиссия, бонусы."""
    seller_price: Optional[FinanceAccrualMoney] = None
    sale_price: Optional[FinanceAccrualMoney] = None
    sale_commission: Optional[FinanceAccrualMoney] = None
    commission: Optional[FinanceAccrualMoney] = None
    commission_ratio: Optional[str] = None
    sale_amount: Optional[FinanceAccrualMoney] = None
    coinvestment: Optional[FinanceAccrualMoney] = None
    bonus: Optional[FinanceAccrualMoney] = None


class FinanceAccrualProductDelivery(BaseEntity):
    """Услуги доставки по товару."""
    services: list[FinanceAccrualFee] = []
    total_accrued: Optional[FinanceAccrualMoney] = None


class FinanceAccrualProduct(BaseEntity):
    sku: Optional[int] = None
    delivery: Optional[FinanceAccrualProductDelivery] = None
    commission: Optional[FinanceAccrualProductCommission] = None


class FinanceAccrualPosting(BaseEntity):
    """Отправление."""
    delivery_schema: Optional[str] = None
    delivery_speed: Optional[int] = None
    products: list[FinanceAccrualProduct] = []


class FinanceAccrual(BaseEntity):
    """Начисление за день (/v1/finance/accrual/by-day)."""
    accrual_id: Optional[int] = None
    accrued_category: Optional[str] = None       # POSTING / ITEM / NON_ITEM
    date: Optional[str] = None
    unit_number: Optional[str] = None            # номер отправления / поставки / заказа
    total_amount: Optional[FinanceAccrualMoney] = None
    posting: Optional[FinanceAccrualPosting] = None
    item_fees: Optional[FinanceAccrualItemFees] = None
    non_item_fee: Optional[FinanceAccrualFee] = None
    container_fees: Optional[FinanceAccrualContainerFees] = None


class FinanceAccrualType(BaseEntity):
    """Элемент справочника начислений (/v1/finance/accrual/types)."""
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None


class FinanceAccrualPostingLine(BaseEntity):
    """Строка начисления по отправлению (/v1/finance/accrual/postings)."""
    accrual_date: Optional[str] = None
    accrued: Optional[FinanceAccrualMoney] = None
    quantity: Optional[int] = None
    seller_price: Optional[FinanceAccrualMoney] = None
    sku: Optional[int] = None
    type_id: Optional[int] = None


class FinanceAccrualPostingAccruals(BaseEntity):
    accruals: list[FinanceAccrualPostingLine] = []
    posting_number: Optional[str] = None
