import time
import logging
import datetime
import numpy as np

from typing import Type
from functools import wraps

from sqlalchemy.orm import Session
from pyodbc import Error as PyodbcError
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine, text, func
from sqlalchemy.dialects.postgresql import insert

from config import *
from data_classes import *
from database.models import *

logger = logging.getLogger(__name__)


def retry_on_exception(retries=3, delay=10):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            attempt = 0
            while attempt < retries:
                try:
                    result = func(self, *args, **kwargs)
                    return result
                except (OperationalError, PyodbcError) as e:
                    attempt += 1
                    logger.debug(f"Error occurred: {e}. Retrying {attempt}/{retries} after {delay} seconds...")
                    time.sleep(delay)
                    if hasattr(self, 'session'):
                        self.session.rollback()
                except Exception as e:
                    logger.error(f"An unexpected error occurred: {e}. Rolling back...")
                    if hasattr(self, 'session'):
                        self.session.rollback()
                    raise e
            raise RuntimeError("Max retries exceeded. Operation failed.")

        return wrapper

    return decorator


class DbConnection:
    def __init__(self, echo: bool = False) -> None:
        self.engine = create_engine(url=DB_URL, echo=echo, pool_pre_ping=True)
        self.session = Session(self.engine)

    @retry_on_exception()
    def start_db(self) -> None:
        """Создание таблиц."""
        metadata.create_all(self.session.bind, checkfirst=True)

    @retry_on_exception()
    def get_client(self, client_id: str) -> Type[Client]:
        """
            Возвращает данные кабинета, отфильтрованный по ID кабинета.

            Args:
                client_id (str): ID кабинета для фильтрации.

            Returns:
                Type[Client]: данные кабинета, удовлетворяющих условию фильтрации.
        """
        client = self.session.query(Client).filter_by(client_id=client_id).first()
        return client

    @retry_on_exception()
    def get_clients(self, marketplace: str = None) -> list[Type[Client]]:
        """
            Возвращает список данных кабинета, отфильтрованный по заданному рынку.

            Args:
                marketplace (str): Рынок для фильтрации.

            Returns:
                List[Type[Client]]: Список данных кабинета, удовлетворяющих условию фильтрации.
        """
        if marketplace:
            result = self.session.query(Client).filter_by(marketplace=marketplace).all()
        else:
            result = self.session.query(Client).all()
        return result

    @retry_on_exception()
    def get_orders(self, from_date: datetime.date) -> list[DataOrder]:
        """
            Получает данные из orders_from_card_stat.

            Args:
                from_date (datetime.date): Дата за которую нужна статиситка.
            Returns:
                List[DataOrder]: Список данных по заказам.
        """
        clients = {client.client_id: client for client in self.get_clients()}
        query = text("SELECT client_id, vendor_code, orders_count FROM orders_from_card_stat WHERE date = :from_date")
        result = self.session.execute(query, {'from_date': from_date.isoformat()}).fetchall()
        return [DataOrder(client=clients[row[0]], vendor_code=row[1], orders_count=row[2]) for row in result]

    @retry_on_exception()
    def get_link_wb_card_product(self) -> dict:
        """
            Получает данные из wb_card_product.

            Returns:
                dict: Словарь артикул: ссылка на товар.
        """
        result = self.session.query(WBCardProduct.vendor_code,
                                    WBCardProduct.link).filter(WBCardProduct.is_work.is_(True)).all()
        final = {}
        for row in result:
            vendor = row.vendor_code.lower().strip()
            final.setdefault(vendor, [])
            final[vendor].append(row.link)
        return final

    @retry_on_exception()
    def get_vendors(self) -> list[str]:
        """
            Получает данные из vendor_code.

            Returns:
                List[str]: Список артикулов.
        """
        query = text("SELECT * FROM vendor_code")
        result = self.session.execute(query).fetchall()
        return [row[0] for row in result]

    @retry_on_exception()
    def get_plan_sale(self) -> list[DataPlanSale]:
        """
            Получает данные по плану продаж из БД.

            Returns:
                List[DataPlanSale]: Список данных по плану продаж.
        """
        result = []

        query_supplies = text("SELECT * FROM supplies")
        result_supplies = self.session.execute(query_supplies).fetchall()
        map_supplies = {(row[0], row[1]): row[2] for row in result_supplies}

        query_sales_plan = text("SELECT * FROM sales_plan_view ORDER BY vendor_code ASC, date ASC")
        result_sales_plan = self.session.execute(query_sales_plan).fetchall()

        for row in result_sales_plan:
            result.append(DataPlanSale(date=row[0],
                                       vendor_code=row[1],
                                       quantity_plan=row[2],
                                       price_plan=round(float(row[3]), 2),
                                       sum_price_plan=round(float(row[4]), 2),
                                       profit_proc=round(float(row[5]), 2),
                                       profit=round(float(row[6]), 2),
                                       supplies=map_supplies.get((row[0], row[1]), '')))

        return result

    @retry_on_exception()
    def get_last_date_commodity_assets(self) -> datetime.date:
        """
            Получает дату последнего обновления остатков на FBS.

            Returns:
                datetime.date: дата последнего обновления остатков на FBS.
        """
        result = self.session.query(func.max(CommodityAssets.date)).scalar()
        return result

    @retry_on_exception()
    def get_stocks(self, from_date: datetime.date) -> dict[str, int]:
        """
            Получает словарь артикулов с остатками товара за дату.

            Args:
                from_date (datetime.date): Дата за которую нужна информация.

            Returns:
                Dict[str, int]: Словарь артикулов с остатками на складах.
        """
        query = text("""
            SELECT vendor_code, SUM(total_quantity) as quantity
            FROM stocks_view_final 
            WHERE date = :from_date
            GROUP BY vendor_code
        """)
        result = self.session.execute(query, {"from_date": from_date}).fetchall()
        return {row[0]: int(row[1]) for row in result}

    @retry_on_exception()
    def get_plan(self, from_date: datetime.date) -> dict[str, int]:
        """
            Получает словарь артикулов с планом продаж за дату.

            Args:
                from_date (datetime.date): Дата за которую нужна информация.

            Returns:
                Dict[str, int]: Словарь артикулов с планом продаж.
        """
        query = text("""
            SELECT sp.vendor_code, sp.quantity_plan
            FROM sales_plan sp
            INNER JOIN (
                SELECT vendor_code, MAX(date) AS max_date
                FROM sales_plan
                WHERE date <= :from_date
                GROUP BY vendor_code
            ) t
                ON sp.vendor_code = t.vendor_code
               AND sp.date = t.max_date
        """)

        result = self.session.execute(query, {"from_date": from_date}).fetchall()

        return {row[0]: int(row[1]) for row in result}

    @retry_on_exception()
    def get_analytics(self, from_date: datetime.date) -> dict[str, str]:
        """
            Получает словарь артикулов с аналитикой продаж за 14 дневный период с переданной даты.

            Args:
                from_date (datetime.date): Конечная дата периода.

            Returns:
                Dict[str, int]: Словарь артикулов с аналитикой продаж.
        """
        plan = self.get_plan(from_date=from_date)

        query_analytics = text("""
            SELECT vendor_code, date, quantities
            FROM google_12_na_273 
            WHERE date > :from_date
            ORDER BY vendor_code, date ASC
        """)
        result_analytics = self.session.execute(
            query_analytics, {"from_date": from_date - datetime.timedelta(days=14)}).fetchall()

        map_analytics = {}

        for row in result_analytics:
            if row[0] not in plan:
                continue
            map_analytics.setdefault(row[0], {})
            map_analytics[row[0]].setdefault(row[1], int(row[2]))

        data_analytics = {}

        for key, values in map_analytics.items():
            data_analytics.setdefault(key, [])
            for day in range(13, -1, -1):
                data_analytics[key].append(map_analytics[key].get(from_date - datetime.timedelta(days=day), 0))

        analytics = {}

        for key, values in data_analytics.items():
            avg_plan = plan.get(key, 0)
            if not avg_plan:
                continue

            analytics.setdefault(key, "")

            week1 = values[:7]
            avg_week1 = np.mean(week1)

            week2 = values[7:]
            avg_week2 = np.mean(week2)

            proc_plan = avg_week2 / avg_plan

            if proc_plan >= 1.5:
                analytics[key] += "Значительно выше плана."
            elif 1.5 > proc_plan >= 1.15:
                analytics[key] += "Выше плана."
            elif 1.15 > proc_plan >= 0.9:
                analytics[key] += "По плану."
            elif 0.9 > proc_plan >= 0.6:
                analytics[key] += "Ниже плана."
            elif 0.6 > proc_plan >= 0.4:
                analytics[key] += "Половина от плана."
            elif 0.4 > proc_plan >= 0.15:
                analytics[key] += "Ниже половины от плана."
            else:
                analytics[key] += "Далеко от плана."

            if proc_plan > 0.15 and avg_week1 > avg_plan * 0.15:
                proc_weeks = avg_week2 / avg_week1

                if proc_weeks >= 2:
                    analytics[key] += " Значительный рост продаж."
                elif 2 > proc_weeks >= 1.3:
                    analytics[key] += " Рост продаж."
                elif 0.7 > proc_weeks >= 0.3:
                    analytics[key] += " Спад продаж."
                elif 0.3 > proc_weeks:
                    analytics[key] += " Значительный спад продаж."

        return analytics

    @retry_on_exception()
    def add_cost_price(self, list_cost_price: list[DataCostPrice]) -> None:
        """
            Добавляет себестоймость товаров в БД.

            Args:
                list_cost_price (list[DataCostPrice]): список данных по себестоймости.
        """
        for row in list_cost_price:
            stmt = insert(CostPrice).values(
                month_date=row.month_date,
                year_date=row.year_date,
                vendor_code=row.vendor_code,
                cost=row.cost
            ).on_conflict_do_update(
                index_elements=['month_date', 'year_date', 'vendor_code'],
                set_={'cost': row.cost}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_self_purchase(self, list_self_purchase: list[DataSelfPurchase]) -> None:
        for row in list_self_purchase:
            stmt = insert(SelfPurchase).values(
                client_id=row.client_id,
                order_date=row.order_date,
                accrual_date=row.accrual_date,
                vendor_code=row.vendor_code,
                quantities=row.quantities,
                price=row.price
            ).on_conflict_do_update(
                index_elements=['client_id', 'order_date', 'accrual_date', 'vendor_code', 'price'],
                set_={'quantities': row.quantities}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_overseas_purchases(self, list_purchase: list[DataOverseasPurchase]) -> None:
        for row in list_purchase:
            stmt = insert(OverseasPurchase).values(
                accrual_date=row.accrual_date,
                vendor_code=row.vendor_code,
                quantities=row.quantities,
                price=row.price,
                log_cost=row.log_cost,
                log_add_cost=row.log_add_cost
            ).on_conflict_do_update(
                index_elements=['accrual_date', 'vendor_code'],
                set_={'quantities': row.quantities,
                      'price': row.price,
                      'log_cost': row.log_cost,
                      'log_add_cost': row.log_add_cost}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_exchange_rate(self, list_rate: list[DataRate]) -> None:
        for row in list_rate:
            stmt = insert(ExchangeRate).values(
                date=row.date,
                currency=row.currency,
                rate=row.rate
            ).on_conflict_do_nothing(index_elements=['date', 'currency'])
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_commodity_assets(self, list_assets: list[DataCommodityAsset]) -> None:
        if not list_assets:
            return
        self.session.query(CommodityAssets).filter(
            CommodityAssets.date == list_assets[0].date).delete(synchronize_session=False)
        self.session.commit()

        for row in list_assets:
            stmt = insert(CommodityAssets).values(
                date=row.date,
                vendor_code=row.vendor_code,
                fbs=row.fbs,
                on_the_way=row.on_the_way
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_supplies(self, list_supplies: list[DataSupply]) -> None:
        if not list_supplies:
            return
        self.session.query(Supplies).delete(synchronize_session=False)
        self.session.commit()
        for row in list_supplies:
            stmt = insert(Supplies).values(
                date=row.date,
                vendor_code=row.vendor_code,
                supplies=row.supplies
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")
