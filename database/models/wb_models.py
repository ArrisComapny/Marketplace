from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Column, Integer, String, Date, ForeignKey, Numeric, Identity, UniqueConstraint, Boolean, \
    DateTime, Index, text

from .general_models import Base


class WBNegative(Base):
    """Модель таблицы wb_negative."""
    __tablename__ = 'wb_negative'

    client_id = Column(String(length=255), ForeignKey('clients.client_id'), primary_key=True)
    api_key = Column(String(length=1000), nullable=False)
    work = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint('api_key', name='api_key_unique'),
    )


class WBMain(Base):
    """Модель таблицы wb_main_table."""
    __tablename__ = 'wb_main_table'

    id = Column(Integer, Identity(), primary_key=True)
    accrual_date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    type_of_transaction = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    posting_number = Column(String(length=255), nullable=False)
    delivery_schema = Column(String(length=255), nullable=False)
    sku = Column(String(length=255), nullable=False)
    sale = Column(Numeric(precision=12, scale=2), nullable=False)
    quantities = Column(Integer, nullable=False)
    commission = Column(Numeric(precision=12, scale=2), default=None, nullable=True)

    __table_args__ = (
        UniqueConstraint('accrual_date', 'type_of_transaction', 'posting_number', 'sku', name='wb_main_table_unique'),
    )


class WBCardProduct(Base):
    """Модель таблицы wb_card_product."""
    __tablename__ = 'wb_card_product'

    sku = Column(String(length=255), primary_key=True)
    vendor_code = Column(String(length=255), nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    link = Column(String(length=255), default=None, nullable=True)
    price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    discount_price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    is_work = Column(Boolean, default=None, nullable=True)


class WBStatisticCardProduct(Base):
    """Модель таблицы wb_statistic_card_product."""
    __tablename__ = 'wb_statistic_card_product'

    id = Column(Integer, Identity(), primary_key=True)
    sku = Column(String(length=255), ForeignKey('wb_card_product.sku'), nullable=False)
    date = Column(Date, nullable=False)
    open_card_count = Column(Integer, nullable=False)
    add_to_cart_count = Column(Integer, nullable=False)
    orders_count = Column(Integer, nullable=False)
    buyouts_count = Column(Integer, nullable=False)
    cancel_count = Column(Integer, nullable=False)
    orders_sum = Column(Numeric(precision=12, scale=2), nullable=False)
    price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    discount_price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)

    __table_args__ = (
        UniqueConstraint('sku', 'date', 'client_id', name='wb_statistic_card_product_unique'),
    )


class WBAdverts(Base):
    """Модель таблицы wb_adverts_table."""
    __tablename__ = 'wb_adverts_table'

    id_advert = Column(String(length=255), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    id_type = Column(Integer, ForeignKey('wb_type_advert.id_type'), nullable=False)
    id_status = Column(Integer, ForeignKey('wb_status_advert.id_status'), nullable=False)
    name_advert = Column(String(length=1000), default=None, nullable=True)
    create_time = Column(Date, nullable=False)
    change_time = Column(Date, nullable=False)
    start_time = Column(Date, nullable=False)
    end_time = Column(Date, nullable=True)


class WBTypeAdvert(Base):
    """Модель таблицы wb_type_advert."""
    __tablename__ = 'wb_type_advert'

    id_type = Column(Integer, primary_key=True)
    type = Column(String(length=255), default=None, nullable=True)


class WBStatusAdvert(Base):
    """Модель таблицы wb_status_advert."""
    __tablename__ = 'wb_status_advert'

    id_status = Column(Integer, primary_key=True)
    status = Column(String(length=255), default=None, nullable=True)


class WBStatisticAdvert(Base):
    """Модель таблицы wb_statistic_advert."""
    __tablename__ = 'wb_statistic_advert'

    id = Column(Integer, Identity(), primary_key=True)
    sku = Column(String(length=255), ForeignKey('wb_card_product.sku'), nullable=False)
    advert_id = Column(String(length=255), ForeignKey('wb_adverts_table.id_advert'), nullable=False)
    date = Column(Date, nullable=False)
    views = Column(Integer, nullable=False)
    clicks = Column(Integer, nullable=False)
    atbs = Column(Integer, nullable=False)
    orders_count = Column(Integer, nullable=False)
    shks = Column(Integer, nullable=False)
    sum_price = Column(Numeric(precision=12, scale=2), nullable=False)
    sum_cost = Column(Numeric(precision=12, scale=2), nullable=False)
    appType = Column(String(length=255), nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)

    __table_args__ = (
        UniqueConstraint('sku', 'advert_id', 'date', 'appType', name='wb_statistic_advert_unique'),
    )


class WBReport(Base):
    """Модель таблицы wb_report."""
    __tablename__ = 'wb_report'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    realizationreport_id = Column(String(length=255), default=None, nullable=True)
    gi_id = Column(String(length=255), default=None, nullable=True)
    subject_name = Column(String(length=255), default=None, nullable=True)
    sku = Column(String(length=255), nullable=False)
    brand = Column(String(length=255), default=None, nullable=True)
    vendor_code = Column(String(length=255), nullable=False)
    size = Column(String(length=255), default=None, nullable=True)
    barcode = Column(String(length=255), default=None, nullable=True)
    doc_type_name = Column(String(length=255), default=None, nullable=True)
    quantity = Column(Integer, nullable=False)
    retail_price = Column(Numeric(precision=12, scale=2), nullable=False)
    retail_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    sale_percent = Column(Integer, nullable=False)
    commission_percent = Column(Numeric(precision=12, scale=2), nullable=False)
    office_name = Column(String(length=255), default=None, nullable=True)
    supplier_oper_name = Column(String(length=255), nullable=False)
    order_date = Column(Date, nullable=False)
    sale_date = Column(Date, nullable=False)
    operation_date = Column(Date, nullable=False)
    shk_id = Column(String(length=255), default=None, nullable=True)
    retail_price_withdisc_rub = Column(Numeric(precision=12, scale=2), nullable=False)
    delivery_amount = Column(Integer, nullable=False)
    return_amount = Column(Integer, nullable=False)
    delivery_rub = Column(Numeric(precision=12, scale=2), nullable=False)
    gi_box_type_name = Column(String(length=255), default=None, nullable=True)
    product_discount_for_report = Column(Numeric(precision=12, scale=2), nullable=False)
    supplier_promo = Column(Numeric(precision=12, scale=2), nullable=False)
    order_id = Column(String(length=255), default=None, nullable=True)
    ppvz_spp_prc = Column(Numeric(precision=12, scale=2),  nullable=False)
    ppvz_kvw_prc_base = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_kvw_prc = Column(Numeric(precision=12, scale=2), nullable=False)
    sup_rating_prc_up = Column(Numeric(precision=12, scale=2), nullable=False)
    is_kgvp_v2 = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_sales_commission = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_for_pay = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_reward = Column(Numeric(precision=12, scale=2), nullable=False)
    acquiring_fee = Column(Numeric(precision=12, scale=2), nullable=False)
    acquiring_bank = Column(String(length=255), default=None, nullable=True)
    ppvz_vw = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_vw_nds = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_office_id = Column(String(length=255), default=None, nullable=True)
    ppvz_office_name = Column(String(length=255), default=None, nullable=True)
    ppvz_supplier_id = Column(String(length=255), default=None, nullable=True)
    ppvz_supplier_name = Column(String(length=255), default=None, nullable=True)
    ppvz_inn = Column(String(length=255), default=None, nullable=True)
    declaration_number = Column(String(length=255), default=None, nullable=True)
    bonus_type_name = Column(String(length=1000), default=None, nullable=True)
    sticker_id = Column(String(length=255), default=None, nullable=True)
    site_country = Column(String(length=255), default=None, nullable=True)
    penalty = Column(Numeric(precision=12, scale=2), nullable=False)
    additional_payment = Column(Numeric(precision=12, scale=2), nullable=False)
    rebill_logistic_cost = Column(Numeric(precision=12, scale=2), nullable=False)
    rebill_logistic_org = Column(String(length=255), default=None, nullable=True)
    kiz = Column(String(length=255), default=None, nullable=True)
    storage_fee = Column(Numeric(precision=12, scale=2), nullable=False)
    deduction = Column(Numeric(precision=12, scale=2), nullable=False)
    acceptance = Column(Numeric(precision=12, scale=2), nullable=False)
    posting_number = Column(String(length=255), nullable=False)


class WBReportDaily(Base):
    """Модель таблицы wb_report_daily (ежедневный детализированный отчёт)."""
    __tablename__ = 'wb_report_daily'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    realizationreport_id = Column(String(length=255), default=None, nullable=True)
    gi_id = Column(String(length=255), default=None, nullable=True)
    subject_name = Column(String(length=255), default=None, nullable=True)
    sku = Column(String(length=255), nullable=False)
    brand = Column(String(length=255), default=None, nullable=True)
    vendor_code = Column(String(length=255), nullable=False)
    size = Column(String(length=255), default=None, nullable=True)
    barcode = Column(String(length=255), default=None, nullable=True)
    doc_type_name = Column(String(length=255), default=None, nullable=True)
    quantity = Column(Integer, nullable=False)
    retail_price = Column(Numeric(precision=12, scale=2), nullable=False)
    retail_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    sale_percent = Column(Integer, nullable=False)
    commission_percent = Column(Numeric(precision=12, scale=2), nullable=False)
    office_name = Column(String(length=255), default=None, nullable=True)
    supplier_oper_name = Column(String(length=255), nullable=False)
    order_date = Column(Date, nullable=False)
    sale_date = Column(Date, nullable=False)
    operation_date = Column(Date, nullable=False)
    shk_id = Column(String(length=255), default=None, nullable=True)
    retail_price_withdisc_rub = Column(Numeric(precision=12, scale=2), nullable=False)
    delivery_amount = Column(Integer, nullable=False)
    return_amount = Column(Integer, nullable=False)
    delivery_rub = Column(Numeric(precision=12, scale=2), nullable=False)
    gi_box_type_name = Column(String(length=255), default=None, nullable=True)
    product_discount_for_report = Column(Numeric(precision=12, scale=2), nullable=False)
    supplier_promo = Column(Numeric(precision=12, scale=2), nullable=False)
    order_id = Column(String(length=255), default=None, nullable=True)
    ppvz_spp_prc = Column(Numeric(precision=12, scale=2),  nullable=False)
    ppvz_kvw_prc_base = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_kvw_prc = Column(Numeric(precision=12, scale=2), nullable=False)
    sup_rating_prc_up = Column(Numeric(precision=12, scale=2), nullable=False)
    is_kgvp_v2 = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_sales_commission = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_for_pay = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_reward = Column(Numeric(precision=12, scale=2), nullable=False)
    acquiring_fee = Column(Numeric(precision=12, scale=2), nullable=False)
    acquiring_bank = Column(String(length=255), default=None, nullable=True)
    ppvz_vw = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_vw_nds = Column(Numeric(precision=12, scale=2), nullable=False)
    ppvz_office_id = Column(String(length=255), default=None, nullable=True)
    ppvz_office_name = Column(String(length=255), default=None, nullable=True)
    ppvz_supplier_id = Column(String(length=255), default=None, nullable=True)
    ppvz_supplier_name = Column(String(length=255), default=None, nullable=True)
    ppvz_inn = Column(String(length=255), default=None, nullable=True)
    declaration_number = Column(String(length=255), default=None, nullable=True)
    bonus_type_name = Column(String(length=1000), default=None, nullable=True)
    sticker_id = Column(String(length=255), default=None, nullable=True)
    site_country = Column(String(length=255), default=None, nullable=True)
    penalty = Column(Numeric(precision=12, scale=2), nullable=False)
    additional_payment = Column(Numeric(precision=12, scale=2), nullable=False)
    rebill_logistic_cost = Column(Numeric(precision=12, scale=2), nullable=False)
    rebill_logistic_org = Column(String(length=255), default=None, nullable=True)
    kiz = Column(String(length=255), default=None, nullable=True)
    storage_fee = Column(Numeric(precision=12, scale=2), nullable=False)
    deduction = Column(Numeric(precision=12, scale=2), nullable=False)
    acceptance = Column(Numeric(precision=12, scale=2), nullable=False)
    posting_number = Column(String(length=255), nullable=False)


class WBTypeServices(Base):
    """Модель таблицы wb_type_services."""
    __tablename__ = 'wb_type_services'

    id = Column(Integer, Identity(), primary_key=True)
    operation_type = Column(String(length=255), nullable=False)
    service = Column(String(length=1000), default=None, nullable=True)
    type_name = Column(String(length=255), default=None, nullable=True)


class WBStorage(Base):
    """Модель таблицы wb_storage."""
    __tablename__ = 'wb_storage'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    date = Column(Date, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    sku = Column(String(length=255), nullable=False)
    calc_type = Column(String(length=255), nullable=False)
    cost = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'sku', 'calc_type', name='wb_storage_unique'),
    )


class WBOrders(Base):
    """Модель таблицы wb_orders."""
    __tablename__ = 'wb_orders'

    id = Column(Integer, Identity(), primary_key=True)
    order_date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    sku = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    category = Column(String(length=255), nullable=False)
    subject = Column(String(length=255), nullable=False)
    posting_number = Column(String(length=255), nullable=False)
    price = Column(Numeric(precision=12, scale=2), nullable=False)
    is_cancel = Column(Boolean, nullable=True)
    cancel_date = Column(Date, nullable=True)
    warehouse = Column(String(length=255), nullable=True)
    warehouse_type = Column(String(length=255), nullable=True)
    country = Column(String(length=255), nullable=True)
    oblast = Column(String(length=255), nullable=True)
    region = Column(String(length=255), nullable=True)

    __table_args__ = (
        UniqueConstraint('order_date', 'sku', 'posting_number', name='wb_orders_unique'),
    )


class WBAcceptance(Base):
    """Модель таблицы wb_acceptance."""
    __tablename__ = 'wb_acceptance'

    id = Column(Integer, Identity(), primary_key=True)
    date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    sku = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), default=None, nullable=True)
    cost = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'sku', name='wb_acceptance_unique'),
    )


class WBStock(Base):
    """Модель таблицы wb_stocks."""
    __tablename__ = 'wb_stocks'

    id = Column(Integer, Identity(), primary_key=True)
    date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    sku = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    size = Column(String(length=255), nullable=False)
    category = Column(String(length=255), nullable=False)
    subject = Column(String(length=255), nullable=False)
    warehouse = Column(String(length=255), nullable=False)
    quantity_warehouse = Column(Integer, nullable=False)
    quantity_to_client = Column(Integer, nullable=False)
    quantity_from_client = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('client_id', 'date', 'sku', 'warehouse', 'size', name='wb_stocks_unique'),
    )


class WBOrderFBS(Base):
    """Модель таблицы wb_fbs_orders."""
    __tablename__ = 'wb_fbs_orders'

    id = Column(Integer, Identity(), primary_key=True)
    order_id = Column(String(length=255), nullable=False)
    supply_id = Column(String(length=255), nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    warehouse_id = Column(String(length=255), nullable=False)
    order_date = Column(DateTime, nullable=False)
    posting_number = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    sku = Column(String(length=255), nullable=False)
    barcodes = Column(ARRAY(String), default=list, nullable=False)
    status = Column(String(length=255), nullable=True)

    __table_args__ = (
        UniqueConstraint('order_id', 'client_id', name='wb_fbs_orders_unique'),
    )


class WBWarehouseFBS(Base):
    """Модель таблицы wb_fbs_warehouses."""
    __tablename__ = 'wb_fbs_warehouses'

    warehouse_id = Column(String(length=255), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    name = Column(String(length=255), nullable=False)
    office_id = Column(String(length=255), nullable=False)
    cargo_type = Column(String(length=255), nullable=False)
    delivery_type = Column(String(length=255), nullable=False)


class WBSupplyFBS(Base):
    """Модель таблицы wb_fbs_supplies."""
    __tablename__ = 'wb_fbs_supplies'

    supply_id = Column(String(length=255), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    done = Column(Boolean)
    created_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    scan_dt = Column(DateTime, nullable=True)
    name = Column(String(length=255), nullable=False)
    cargo_type = Column(String(length=255), nullable=False)


class WBStockFBS(Base):
    """Модель таблицы wb_fbs_stocks."""
    __tablename__ = 'wb_fbs_stocks'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    warehouse_id = Column(String(length=255), nullable=False)
    barcode = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=True)
    date = Column(Date, nullable=False)
    count = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('client_id', 'warehouse_id', 'barcode', 'date', name='wb_fbs_stocks_unique'),
    )


class WBSupply(Base):
    """Модель таблицы wb_supplies."""
    __tablename__ = 'wb_supplies'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    supply_id = Column(String(length=255), default=None, nullable=True)
    preorder_id = Column(String(length=255), nullable=False)
    phone = Column(String(length=255), default=None, nullable=True)
    create_date = Column(DateTime, nullable=False)
    supply_date = Column(DateTime, default=None, nullable=True)
    fact_date = Column(DateTime, default=None, nullable=True)
    updated_date = Column(DateTime, default=None, nullable=True)
    status_id = Column(Integer, nullable=False)
    box_type_id = Column(Integer, default=None, nullable=True)
    is_box_on_pallet = Column(Boolean, default=None, nullable=True)

    __table_args__ = (
        # Поставка с заказом идентифицируется по preorder_id (supply_id появляется позже),
        # поставка без заказа (preorder_id = '0') — по supply_id
        Index('wb_supplies_preorder_unique', 'preorder_id', unique=True,
              postgresql_where=text("preorder_id != '0'")),
        Index('wb_supplies_supply_unique', 'supply_id', unique=True,
              postgresql_where=text("preorder_id = '0'")),
    )


class WBSupplyDetails(Base):
    """Модель таблицы wb_supplies_details."""
    __tablename__ = 'wb_supplies_details'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    supply_id = Column(String(length=255), nullable=False)
    warehouse_id = Column(Integer, default=None, nullable=True)
    warehouse_name = Column(String(length=255), default=None, nullable=True)
    actual_warehouse_id = Column(Integer, default=None, nullable=True)
    actual_warehouse_name = Column(String(length=255), default=None, nullable=True)
    acceptance_cost = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    paid_acceptance_coefficient = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    storage_coef = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    delivery_coef = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    reject_reason = Column(String(length=1000), default=None, nullable=True)
    supplier_assign_name = Column(String(length=255), default=None, nullable=True)
    quantity = Column(Integer, default=None, nullable=True)
    accepted_quantity = Column(Integer, default=None, nullable=True)
    unloading_quantity = Column(Integer, default=None, nullable=True)
    ready_for_sale_quantity = Column(Integer, default=None, nullable=True)
    depersonalized_quantity = Column(Integer, default=None, nullable=True)
    virtual_type_id = Column(Integer, default=None, nullable=True)
    updated_date = Column(DateTime, default=None, nullable=True)

    __table_args__ = (
        UniqueConstraint('supply_id', name='wb_supplies_details_unique'),
    )


class WBSupplyGoods(Base):
    """Модель таблицы wb_supplies_goods."""
    __tablename__ = 'wb_supplies_goods'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    supply_id = Column(String(length=255), nullable=False)
    barcode = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), default=None, nullable=True)
    sku = Column(String(length=255), default=None, nullable=True)
    tech_size = Column(String(length=255), default=None, nullable=True)
    color = Column(String(length=255), default=None, nullable=True)
    need_kiz = Column(Boolean, default=None, nullable=True)
    supplier_box_amount = Column(Integer, default=None, nullable=True)
    quantity = Column(Integer, default=None, nullable=True)
    accepted_quantity = Column(Integer, default=None, nullable=True)
    unloading_quantity = Column(Integer, default=None, nullable=True)
    ready_for_sale_quantity = Column(Integer, default=None, nullable=True)

    __table_args__ = (
        UniqueConstraint('supply_id', 'barcode', name='wb_supplies_goods_unique'),
    )
