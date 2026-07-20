from sqlalchemy.orm import declarative_base
from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy import Column, String, MetaData, Integer, Identity, Numeric, ForeignKey, Date, Boolean

metadata = MetaData()
Base = declarative_base(metadata=metadata)


class Client(Base):
    """Модель таблицы clients."""
    __tablename__ = 'clients'

    client_id = Column(String(length=255), primary_key=True)
    api_key = Column(String(length=1000), nullable=False)
    marketplace = Column(String(length=255), nullable=False)
    name_company = Column(String(length=255), nullable=False)
    entrepreneur = Column(String(length=255), nullable=False)
    tax_type = Column(String(length=255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')


class CostPrice(Base):
    """Модель таблицы cost_price."""
    __tablename__ = 'cost_price'

    id = Column(Integer, Identity(), primary_key=True)
    month_date = Column(Integer, nullable=False)
    year_date = Column(Integer, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    cost = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('month_date', 'year_date', 'vendor_code', name='cost_price_unique'),
    )


class SelfPurchase(Base):
    """Модель таблицы self_purchase."""
    __tablename__ = 'self_purchase'

    id = Column(Integer, Identity(), primary_key=True)
    client_id = Column(String(length=255), ForeignKey('clients.client_id'), nullable=False)
    order_date = Column(Date, nullable=False)
    accrual_date = Column(Date, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    quantities = Column(Integer, nullable=False)
    price = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('client_id', 'order_date', 'accrual_date', 'vendor_code', 'price', name='self_purchase_unique'),
    )


class OverseasPurchase(Base):
    """Модель таблицы overseas_purchase."""
    __tablename__ = 'overseas_purchase'

    id = Column(Integer, Identity(), primary_key=True)
    accrual_date = Column(Date, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    quantities = Column(Integer, nullable=False)
    price = Column(Numeric(precision=12, scale=2), nullable=False)
    log_cost = Column(Numeric(precision=12, scale=2), nullable=False)
    log_add_cost = Column(Numeric(precision=12, scale=2), nullable=False)

    __table_args__ = (
        UniqueConstraint('accrual_date', 'vendor_code', name='overseas_purchase_unique'),
    )


class TypeOfTransaction(Base):
    """Модель таблицы type_of_transaction."""
    __tablename__ = 'type_of_transaction'

    type_of_transaction = Column(String(length=100), primary_key=True)


class ExchangeRate(Base):
    """Модель таблицы exchange_rate."""
    __tablename__ = 'exchange_rate'

    id = Column(Integer, Identity(), primary_key=True)
    date = Column(Date, nullable=False)
    currency = Column(String(length=100), nullable=False)
    rate = Column(Numeric(precision=12, scale=4), nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'currency', name='exchange_rate_unique'),
    )


class Supplies(Base):
    """Модель таблицы supplies."""
    __tablename__ = 'supplies'

    date = Column(Date, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    supplies = Column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('date', 'vendor_code'),
    )


class CommodityAssets(Base):
    """Модель таблицы commodity_assets."""
    __tablename__ = 'commodity_assets'

    id = Column(Integer, Identity(), primary_key=True)
    date = Column(Date, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    fbs = Column(Integer, nullable=False)
    on_the_way = Column(Integer, nullable=False)


class SalesPlan(Base):
    """Модель таблицы sales_plan."""
    __tablename__ = 'sales_plan'

    date = Column(Date, nullable=False)
    vendor_code = Column(String(length=255), nullable=False)
    quantity_plan = Column(Integer, nullable=False)
    price_plan = Column(Numeric(precision=12, scale=2), nullable=False)
    profit_proc = Column(Numeric(precision=12, scale=4), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('date', 'vendor_code'),
    )
