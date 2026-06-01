from datetime import datetime
from typing import Optional

from .base import BaseEntity


class PostingFBSListMoneyValue(BaseEntity):
    """Денежное значение."""
    amount: str = None
    currency: str = None


class PostingFBSListAddressee(BaseEntity):
    """Контактные данные получателя."""
    name: str = None
    phone: str = None


class PostingFBSListAnalyticsData(BaseEntity):
    """Данные аналитики."""
    city: str = None
    client_delivery_date_begin: Optional[datetime] = None
    client_delivery_date_end: Optional[datetime] = None
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


class PostingFBSListBarcodes(BaseEntity):
    """Штрихкоды отправления."""
    lower_barcode: str = None
    upper_barcode: str = None


class PostingFBSListCancellation(BaseEntity):
    """Информация об отмене."""
    affect_cancellation_rating: bool = None
    cancel_reason: str = None
    cancel_reason_id: int = None
    cancellation_initiator: str = None
    cancellation_type: str = None
    cancelled_after_ship: bool = None


class PostingFBSListContainer(BaseEntity):
    """Информация о грузоместе."""
    cargo_type: str = None
    container_date: str = None
    container_id: int = None
    container_number: int = None


class PostingFBSListCustomerAddress(BaseEntity):
    """Информация об адресе доставки."""
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


class PostingFBSListCustomer(BaseEntity):
    """Данные о покупателе."""
    address: Optional[PostingFBSListCustomerAddress] = None
    customer_email: str = None
    customer_id: int = None
    name: str = None
    phone: str = None


class PostingFBSListDeliveryMethod(BaseEntity):
    """Метод доставки."""
    id: int = None
    name: str = None
    tpl_provider: str = None
    tpl_provider_id: int = None
    warehouse: str = None
    warehouse_id: int = None


class PostingFBSListExternalOrder(BaseEntity):
    """Данные о заказе из внешнего магазина."""
    is_external: bool = None
    platform_name: str = None


class PostingFBSListFinancialDataProductCommission(BaseEntity):
    """Комиссия за товар."""
    amount: float = None
    currency: str = None
    percent: float = None


class PostingFBSListFinancialDataProduct(BaseEntity):
    """Информация о товаре в заказе."""
    actions: list[str] = []
    commission: Optional[PostingFBSListFinancialDataProductCommission] = None
    customer_price: Optional[PostingFBSListMoneyValue] = None
    old_price: float = None
    payout: float = None
    price: float = None
    product_id: int = None
    quantity: int = None
    total_discount_percent: float = None
    total_discount_value: float = None


class PostingFBSListFinancialData(BaseEntity):
    """Данные о стоимости товара, размере скидки, выплате и комиссии."""
    cluster_from: str = None
    cluster_to: str = None
    products: list[PostingFBSListFinancialDataProduct] = []


class PostingFBSListLegalInfo(BaseEntity):
    """Данные о юридическом лице покупателя."""
    company_name: str = None
    inn: str = None
    kpp: str = None


class PostingFBSListOptional(BaseEntity):
    """Опциональные данные отправления."""
    products_with_possible_mandatory_mark: list[int] = []


class PostingFBSListProduct(BaseEntity):
    """Товар в отправлении."""
    imei: list[str] = []
    is_blr_traceable: bool = None
    is_marketplace_buyout: bool = None
    name: str = None
    offer_id: str = None
    price: Optional[PostingFBSListMoneyValue] = None
    product_color: str = None
    quantity: int = None
    sku: int = None
    weight: float = None


class PostingFBSListRequirements(BaseEntity):
    """
        Список продуктов, для которых нужно передать дополнительные сведения
        (страна-изготовитель, ГТД, РНПТ, маркировка и т.д.), чтобы перевести
        отправление в следующий статус.
    """
    products_requiring_change_country: list[str] = []
    products_requiring_country: list[str] = []
    products_requiring_gtd: list[str] = []
    products_requiring_imei: list[str] = []
    products_requiring_jw_uin: list[str] = []
    products_requiring_mandatory_mark: list[str] = []
    products_requiring_rnpt: list[str] = []


class PostingFBSListTarifficationCharge(BaseEntity):
    """Текущая и следующая тарификация отправления."""
    current_tariff_charge: Optional[PostingFBSListMoneyValue] = None
    current_tariff_min_charge: Optional[PostingFBSListMoneyValue] = None
    current_tariff_rate: float = None
    current_tariff_type: str = None
    next_tariff_charge: Optional[PostingFBSListMoneyValue] = None
    next_tariff_min_charge: Optional[PostingFBSListMoneyValue] = None
    next_tariff_rate: float = None
    next_tariff_starts_at: Optional[datetime] = None
    next_tariff_type: str = None


class PostingFBSListTarifficationStep(BaseEntity):
    """Шаг тарификации отправления."""
    min_charge: Optional[PostingFBSListMoneyValue] = None
    tariff_charge: Optional[PostingFBSListMoneyValue] = None
    tariff_deadline_at: Optional[datetime] = None
    tariff_rate: float = None
    tariff_type: str = None


class PostingFBSListPosting(BaseEntity):
    """Информация об отправлении."""
    addressee: Optional[PostingFBSListAddressee] = None
    analytics_data: Optional[PostingFBSListAnalyticsData] = None
    available_actions: list[str] = []
    barcodes: Optional[PostingFBSListBarcodes] = None
    cancellation: Optional[PostingFBSListCancellation] = None
    container: Optional[PostingFBSListContainer] = None
    container_sort_type: str = None
    customer: Optional[PostingFBSListCustomer] = None
    delivering_date: Optional[datetime] = None
    delivery_method: Optional[PostingFBSListDeliveryMethod] = None
    delivery_schema: str = None
    destination_place_id: int = None
    destination_place_name: str = None
    external_order: Optional[PostingFBSListExternalOrder] = None
    financial_data: Optional[PostingFBSListFinancialData] = None
    in_process_at: Optional[datetime] = None
    is_click_and_collect: bool = None
    is_express: bool = None
    is_multibox: bool = None
    is_presortable: bool = None
    legal_info: Optional[PostingFBSListLegalInfo] = None
    multi_box_qty: int = None
    optional: Optional[PostingFBSListOptional] = None
    order_id: int = None
    order_number: str = None
    parent_posting_number: str = None
    pickup_code_verified_at: Optional[datetime] = None
    posting_number: str = None
    products: list[PostingFBSListProduct] = []
    prr_option: str = None
    quantum_id: int = None
    require_blr_traceable_attrs: bool = None
    requirements: Optional[PostingFBSListRequirements] = None
    shipment_date: Optional[datetime] = None
    shipment_date_without_delay: Optional[datetime] = None
    status: str = None
    substatus: str = None
    tariffication: Optional[PostingFBSListTarifficationCharge] = None
    tariffication_steps: list[PostingFBSListTarifficationStep] = []
    tpl_integration_type: str = None
    tracking_number: str = None
    volume_weight: float = None
