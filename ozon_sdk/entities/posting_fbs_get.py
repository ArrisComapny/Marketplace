from datetime import datetime
from typing import Optional

from .picking import Picking
from .base import BaseEntity


class PostingFBSGetAdditionalData(BaseEntity):
    """additional_data"""
    key: str = None
    value: str = None


class PostingFBSGetAddressee(BaseEntity):
    """Контактные данные получателя."""
    name: str = None
    phone: str = None


class PostingFBSGetAnalyticsData(BaseEntity):
    """Данные аналитики."""
    city: str = None
    delivery_date_begin: Optional[datetime] = None
    delivery_date_end: Optional[datetime] = None
    delivery_type: str = None
    is_legal: bool = None
    is_premium: bool = None
    payment_type_group_name: str = None
    region: str = None
    tpl_provider: str = None
    tpl_provider_id: int = None
    warehouse: str = None
    warehouse_id: int = None


class PostingFBSGetBarcodes(BaseEntity):
    """Штрихкоды отправления."""
    lower_barcode: str = None
    upper_barcode: str = None


class PostingFBSGetCancellation(BaseEntity):
    """Информация об отмене."""
    affect_cancellation_rating: bool = None
    cancel_reason: str = None
    cancel_reason_id: int = None
    cancellation_initiator: str = None
    cancellation_type: str = None
    cancelled_after_ship: bool = None


class PostingFBSGetCourier(BaseEntity):
    """Данные о курьере."""
    car_model: str = None
    car_number: str = None
    name: str = None
    phone: str = None


class PostingFBSGetCustomerAddress(BaseEntity):
    """"Информация об адресе доставки."""
    address_tail: str = None
    city: str = None
    comment: str = None
    country: str = None
    district: str = None
    latitude: float = None
    longitude: float = None
    provider_pvz_code: str = None
    pvz_code: int = None
    region: str = None
    zip_code: str = None


class PostingFBSGetCustomer(BaseEntity):
    """Данные о покупателе."""
    address: Optional[PostingFBSGetCustomerAddress] = None
    customer_email: str = None
    customer_id: int = None
    name: str = None
    phone: str = None


class PostingFBSGetDeliveryMethod(BaseEntity):
    """Метод доставки."""
    id: int = None
    name: str = None
    tpl_provider: str = None
    tpl_provider_id: int = None
    warehouse: str = None
    warehouse_id: int = None


class PostingFBSGetFinancialDataProduct(BaseEntity):
    """Информация о товаре в заказе"""
    actions: list[str] = []
    currency_code: str = None
    commission_amount: float = None
    commission_percent: float = None
    commissions_currency_code: str = None
    old_price: float = None
    payout: float = None
    picking: Optional[Picking] = None
    price: float = None
    product_id: int = None
    quantity: int = None
    total_discount_percent: float = None
    total_discount_value: float = None
    customer_price: float = None


class PostingFBSGetFinancialData(BaseEntity):
    """Данные о стоимости товара, размере скидки, выплате и комиссии."""
    cluster_from: str = None
    cluster_to: str = None
    products: list[PostingFBSGetFinancialDataProduct] = []


class PostingFBSGetProductExemplarsProductExemplar(BaseEntity):
    """Информация по экземпляру."""
    exemplar_id: int = None
    mandatory_mark: str = None
    gtd: str = None
    is_gtd_absent: bool = None
    rnpt: str = None
    is_rnpt_absent: bool = None


class PostingFBSGetProductExemplarsProduct(BaseEntity):
    """Информация о продукте и его экзмеплярам."""
    exemplars: list[PostingFBSGetProductExemplarsProductExemplar] = []
    sku: int = None


class PostingFBSGetProductExemplars(BaseEntity):
    """Информация по продуктам и их экзмеплярам."""
    products: list[PostingFBSGetProductExemplarsProduct] = []


class PostingFBSGetProductsDimensions(BaseEntity):
    """Размеры товара."""
    height: str = None
    length: str = None
    weight: str = None
    width: str = None


class PostingFBSGetProduct(BaseEntity):
    """Товар в отправлении."""
    dimensions: Optional[PostingFBSGetProductsDimensions] = None
    name: str = None
    offer_id: str = None
    price: str = None
    jw_uin: list[str] = None
    currency_code: str = None
    quantity: int = None
    sku: int = None


class PostingFBSGetPRROption(BaseEntity):
    """
        Информация об услуге погрузочно-разгрузочных работ. \n
        Актуально для КГТ-отправлений с доставкой силами продавца или интегрированной службой.
    """
    code: str = None
    price: str = None
    currency_code: str = None
    floor: str = None


class PostingFBSGetRelatedPostings(BaseEntity):
    """Связанные отправления."""
    related_posting_numbers: list[str] = None


class PostingFBSGetRequirements(BaseEntity):
    """
        Cписок продуктов, для которых нужно передать страну-изготовителя, номер грузовой таможенной декларации (ГТД),
        регистрационный номер партии товара (РНПТ) или маркировку «Честный ЗНАК», чтобы перевести отправление в следующий статус.
    """
    products_requiring_gtd: list[int] = []
    products_requiring_country: list[int] = []
    products_requiring_mandatory_mark: list[int] = []
    products_requiring_jw_uin: list[int] = []
    products_requiring_rnpt: list[int] = []


class PostingFBSGet(BaseEntity):
    """Информация об отправлении."""
    additional_data: list[PostingFBSGetAdditionalData] = []
    addressee: Optional[PostingFBSGetAddressee] = None
    analytics_data: Optional[PostingFBSGetAnalyticsData] = None
    barcodes: Optional[PostingFBSGetBarcodes] = None
    cancellation: Optional[PostingFBSGetCancellation] = None
    courier: Optional[PostingFBSGetCourier] = None
    customer: Optional[PostingFBSGetCustomer] = None
    delivering_date: Optional[datetime] = None
    delivery_method: Optional[PostingFBSGetDeliveryMethod] = None
    delivery_price: str
    financial_data: Optional[PostingFBSGetFinancialData] = None
    in_process_at: datetime = None
    is_express: bool = None
    is_multibox: bool = None
    multi_box_qty: int = None
    order_id: int = None
    order_number: str = None
    parent_posting_number: str = None
    posting_number: str = None
    product_exemplars: Optional[PostingFBSGetProductExemplars] = None
    products: list[PostingFBSGetProduct] = []
    provider_status: str = None
    prr_option: Optional[PostingFBSGetPRROption] = None
    related_postings: Optional[PostingFBSGetRelatedPostings] = None
    requirements: Optional[PostingFBSGetRequirements] = None
    shipment_date: datetime = None
    status: str = None
    substatus: str = None
    tpl_integration_type: str = None
    tracking_number:  str = None
