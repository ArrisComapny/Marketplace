from sqlalchemy import Column, Integer, String, Date, ForeignKey, Numeric, Identity, UniqueConstraint

from .general_models import Base


class OzMain(Base):
    """Модель таблицы oz_main_table."""
    __tablename__ = 'oz_main_table'

    id = Column(Integer, Identity(), primary_key=True)
    accrual_date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    type_of_transaction = Column(String(length=100), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    posting_number = Column(String(length=100), nullable=False)
    delivery_schema = Column(String(length=100), nullable=False)
    sku = Column(String(length=100), nullable=False)
    sale = Column(Numeric(precision=12, scale=2), nullable=False)
    quantities = Column(Integer, nullable=False)
    commission = Column(Numeric(precision=12, scale=2), nullable=False)
    bonus = Column(Numeric(precision=12, scale=2), nullable=True)

    __table_args__ = (
        UniqueConstraint('type_of_transaction', 'posting_number', 'sku', name='oz_main_table_unique'),
    )


class OzPerformance(Base):
    """Модель таблицы date."""
    __tablename__ = 'oz_performance'

    performance_id = Column(String(length=255), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    client_secret = Column(String(length=1000), unique=True, nullable=False)


class OzCardProduct(Base):
    """Модель таблицы oz_card_product."""
    __tablename__ = 'oz_card_product'

    sku = Column(String(length=255), primary_key=True)
    vendor_code = Column(String(length=255), nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    category = Column(String(length=255), default=None, nullable=True)
    brand = Column(String(length=255), default=None, nullable=True)
    link = Column(String(length=255), default=None, nullable=True)
    price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    discount_price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    created_at = Column(Date)


class OzStatisticCardProduct(Base):
    """Модель таблицы oz_statistic_card_product."""
    __tablename__ = 'oz_statistic_card_product'

    id = Column(Integer, Identity(), primary_key=True)
    sku = Column(String(length=255), ForeignKey('oz_card_product.sku'), nullable=False)
    date = Column(Date, nullable=False)
    view_search = Column(Integer, nullable=False)
    view_card = Column(Integer, nullable=False)
    add_to_cart_from_search_count = Column(Integer, nullable=False)
    add_to_cart_from_card_count = Column(Integer, nullable=False)
    orders_count = Column(Integer, nullable=False)
    orders_sum = Column(Numeric(precision=12, scale=2), nullable=False)
    delivered_count = Column(Integer, nullable=False)
    returns_count = Column(Integer, nullable=False)
    cancel_count = Column(Integer, nullable=False)
    price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)
    discount_price = Column(Numeric(precision=12, scale=2), default=None, nullable=True)

    __table_args__ = (
        UniqueConstraint('sku', 'date', name='oz_statistic_card_product_unique'),
    )


class OzAdverts(Base):
    """Модель таблицы oz_adverts_table."""
    __tablename__ = 'oz_adverts_table'

    id_advert = Column(String(length=255), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    field_type = Column(String(length=255), ForeignKey('oz_type_advert.field_type'), nullable=False)
    field_status = Column(String(length=255), ForeignKey('oz_status_advert.field_status'), nullable=False)
    name_advert = Column(String(length=1000), default=None, nullable=True)
    create_time = Column(Date, nullable=False)
    change_time = Column(Date, nullable=False)
    start_time = Column(Date, default=None, nullable=True)
    end_time = Column(Date, default=None, nullable=True)


class OzTypeAdvert(Base):
    """Модель таблицы oz_type_advert."""
    __tablename__ = 'oz_type_advert'

    field_type = Column(String(length=255), primary_key=True)
    type = Column(String(length=255), default=None, nullable=True)


class OzStatusAdvert(Base):
    """Модель таблицы oz_status_advert."""
    __tablename__ = 'oz_status_advert'

    field_status = Column(String(length=255), primary_key=True)
    status = Column(String(length=255), default=None, nullable=True)


class OzStatisticAdvert(Base):
    """Модель таблицы oz_statistic_advert."""
    __tablename__ = 'oz_statistic_advert'

    id = Column(Integer, Identity(), primary_key=True)
    sku = Column(String(length=255), ForeignKey('oz_card_product.sku'), nullable=False)
    advert_id = Column(String(length=100), ForeignKey('oz_adverts_table.id_advert'), nullable=False)
    date = Column(Date, nullable=False)
    views = Column(Integer, nullable=False)
    clicks = Column(Integer, nullable=False)
    orders_count = Column(Integer, nullable=False)
    sum_price = Column(Numeric(precision=12, scale=2), nullable=False)
    sum_cost = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('sku', 'advert_id', 'date', name='oz_statistic_advert_unique'),
    )


class OzAdvertDailyBudget(Base):
    """Модель таблицы oz_advert_daily_budget."""
    __tablename__ = 'oz_advert_daily_budget'

    id = Column(Integer, Identity(), primary_key=True)
    date = Column(Date, nullable=False)
    advert_id = Column(String(length=100), ForeignKey('oz_adverts_table.id_advert'), nullable=False)
    daily_budget = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'advert_id', name='oz_advert_daily_budget_unique'),
    )


class OzStorage(Base):
    """Модель таблицы oz_storage."""
    __tablename__ = 'oz_storage'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    date = Column(Date, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    sku = Column(String(length=255), nullable=False)
    cost = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('client_id', 'date', 'sku', name='oz_storage_unique'),
    )


class OzServices(Base):
    """Модель таблицы oz_services."""
    __tablename__ = 'oz_services'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    date = Column(Date, nullable=False)
    operation_type = Column(String(length=255), nullable=False)
    operation_type_name = Column(String(length=1000), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    sku = Column(String(length=255), default='', nullable=False)
    posting_number = Column(String(length=255), default='', nullable=False)
    service = Column(String(length=255), default='', nullable=False)
    cost = Column(Numeric(precision=12, scale=2), default=None, nullable=False)

    __table_args__ = (UniqueConstraint('client_id',
                                       'date',
                                       'operation_type',
                                       'sku',
                                       'posting_number',
                                       'service',
                                       name='oz_services_unique'),)


class OzTypeServices(Base):
    """Модель таблицы oz_type_services."""
    __tablename__ = 'oz_type_services'

    id = Column(Integer, Identity(), primary_key=True)
    operation_type = Column(String(length=255), nullable=False)
    service = Column(String(length=255), default='', nullable=False)
    type_name = Column(String(length=255), default='new', nullable=False)


class OzOrders(Base):
    """Модель таблицы oz_orders."""
    __tablename__ = 'oz_orders'

    id = Column(Integer, Identity(), primary_key=True)
    order_date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    sku = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    posting_number = Column(String(length=255), nullable=False)
    delivery_schema = Column(String(length=100), nullable=False)
    quantities = Column(Integer, nullable=False)
    price = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('order_date', 'sku', 'posting_number', name='oz_orders_unique'),
    )


class OzStock(Base):
    """Модель таблицы oz_stocks."""
    __tablename__ = 'oz_stocks'

    id = Column(Integer, Identity(), primary_key=True)
    date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    sku = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    size = Column(String(length=255), nullable=False)
    quantity = Column(Integer, nullable=False)
    reserved = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'sku', 'size', name='oz_stocks_unique'),
    )


class OzBonus(Base):
    """Модель таблицы oz_bonus."""
    __tablename__ = 'oz_bonus'

    id = Column(Integer, Identity(), primary_key=True)
    date = Column(Date, nullable=False)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    sku = Column(String(length=255), nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    bonus = Column(Numeric(precision=12, scale=2), nullable=False)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    bank_coinvestment = Column(Numeric(precision=12, scale=2), nullable=False)
    proc = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'client_id', 'sku', 'vendor_code', name='oz_bonus_unique'),
    )
