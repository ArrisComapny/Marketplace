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
        self.engine = create_engine(url=DB_URL, echo=echo, pool_pre_ping=True, isolation_level="AUTOCOMMIT")
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
    def get_clients(self, marketplace: str = None, only_active: bool = True) -> list[Type[Client]]:
        """
            Возвращает список данных кабинета, отфильтрованный по заданному рынку.

            Args:
                marketplace (str): Рынок для фильтрации.
                only_active (bool): Возвращать только кабинеты с is_active = True.
                    False — вернуть все, включая отключённые (для разовых выгрузок).

            Returns:
                List[Type[Client]]: Список данных кабинета, удовлетворяющих условию фильтрации.
        """
        query = self.session.query(Client)
        if marketplace:
            query = query.filter_by(marketplace=marketplace)
        if only_active:
            query = query.filter_by(is_active=True)
        return query.all()

    @retry_on_exception()
    def get_exchange_rate(self, from_date: datetime.date, currency: str) -> float | None:
        result = self.session.query(ExchangeRate.rate).filter_by(date=from_date, currency=currency).first()
        return float(result[0]) if result else None

    @retry_on_exception()
    def get_orders(self, from_date: datetime.date, to_date: datetime.date | None = None) -> list[DataOrder]:
        clients = {client.client_id: client for client in self.get_clients()}
        if to_date is None:
            query = text("""
                SELECT client_id, vendor_code, orders_count
                FROM orders_from_card_stat
                WHERE date = :from_date
            """)
            params = {'from_date': from_date.isoformat()}
        else:
            query = text("""
                SELECT client_id, vendor_code, SUM(orders_count) AS orders_count
                FROM orders_from_card_stat
                WHERE date BETWEEN :from_date AND :to_date
                GROUP BY client_id, vendor_code
            """)
            params = {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat()}

        result = self.session.execute(query, params).fetchall()
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
    def get_vendors_map(self) -> dict[str, tuple[str, str]]:
        query = text("""
        SELECT vendor_code, main_vendor_code, type_of_vendor_code 
        FROM ip_vendor_code
        WHERE "group" not in ('new', 'other_trash')
        """)
        result = self.session.execute(query).fetchall()
        return {row[0]: (row[1], row[2]) for row in result}

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
    def get_cost_price(self, on_date: datetime.date) -> dict[str, float]:
        """
            Возвращает {vendor_code (lower): cost_per_unit} за месяц/год указанной даты.

            Args:
                on_date (datetime.date): Дата, по которой берётся месяц/год.

            Returns:
                Dict[str, float]: Себестоимость за единицу по артикулу.
        """
        query = text("""
            SELECT lower(vendor_code) AS vendor_code, cost
            FROM cost_price
            WHERE month_date = :m AND year_date = :y
        """)
        result = self.session.execute(query, {"m": on_date.month, "y": on_date.year}).fetchall()
        return {row[0]: float(row[1]) for row in result}

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
    def get_stocks_detail(self, from_date: datetime.date) -> list[DataStock]:
        """
            Получает остатки на складах за дату.

            FBS-стоки агрегируются под client = 'FBS' (без разделения по продавцу).
            FBO-стоки агрегируются по client = client_id (магазин).
            Строки с marketplace = 'On the way' игнорируются.

            Args:
                from_date (datetime.date): Дата за которую нужна информация.

            Returns:
                List[DataStock]: Список остатков с полями client, vendor_code, quantity.
        """
        query = text("""
            SELECT CASE WHEN marketplace = 'FBS' THEN 'FBS' ELSE client_id END AS client,
                   vendor_code,
                   SUM(quantity) AS quantity
            FROM stocks_view_final
            WHERE date = :from_date
              AND marketplace <> 'On the way'
            GROUP BY CASE WHEN marketplace = 'FBS' THEN 'FBS' ELSE client_id END, vendor_code
        """)
        result = self.session.execute(query, {"from_date": from_date}).fetchall()
        return [DataStock(client=row[0], vendor_code=row[1], quantity=int(row[2])) for row in result]

    @retry_on_exception()
    def get_profit(self, from_date: datetime.date, to_date: datetime.date) -> list[DataProfit]:
        """
            Возвращает компоненты прибыли по (marketplace, client_id, vendor_code) за период.

            profit = sale - cost - commission - acquiring - logistics - storage
                     - advertising - other - tac

            Знаковая логика по МП:
              - WB: commission_raw из main включает acquiring; на выход кладём net
                    (commission = commission_raw - acquiring), acquiring отдельно.
              - OZ: commission и services хранятся отрицательными удержаниями — ABS.
                    acquiring берём из services (type 'acq').
              - YA: commission и acquiring сидят в services (type 'comm'/'acq').
        """
        params = {"f": from_date, "t": to_date}

        # Категоризация type_name в services_final (приведено к нижнему регистру в SQL).
        category_types = {
            'WB': {
                'logistics':   ['log'],
                'storage':     ['storage'],
                'advertising': ['adv_stat'],
                'other':       ['other_pin'],
            },
            'OZON': {
                'acquiring':   ['acq'],
                'logistics':   ['log', 'log_return', 'log_other', 'log_lastmile', 'log_rr'],
                'storage':     ['storage', 'storage_r'],
                'advertising': ['adv_click', 'adv_stat', 'adv_rev', 'adv_bs'],
                'other':       ['other_tc', 'other_sub', 'other_fbo',
                                'other_uti2', 'new', 'other', 'other_co'],
            },
            'YANDEX': {
                'commission':  ['comm'],
                'acquiring':   ['acq'],
                'logistics':   ['log'],
                'storage':     ['stor'],
                'advertising': ['avg'],
            },
        }

        # FIELDS — порядок полей агрегата
        FIELDS = ('sale', 'cost', 'commission', 'acquiring',
                  'logistics', 'storage', 'advertising', 'other', 'tac',
                  'quantities')

        # (mp, client_id, vendor_code) -> {field: value}
        agg: dict[tuple[str, str, str], dict[str, float]] = {}

        def slot(mp: str, cid: str, vc: str) -> dict[str, float]:
            return agg.setdefault((mp, cid, vc), {k: 0.0 for k in FIELDS})

        # --- main_table per МП ---
        # WB: commission_raw и acquiring отдельно (acquiring как самостоятельный расход,
        # commission показываем уже netto = raw - acquiring).
        for cid, vc, sale, cost, comm_raw, acq, tac, qty in self.session.execute(text("""
            SELECT client_id, lower(vendor_code),
                   SUM(sale), SUM(cost), SUM(commission), SUM(acquiring),
                   SUM("TaC"), SUM(quantities)
            FROM wb_main_table_final2
            WHERE accrual_date BETWEEN :f AND :t
            GROUP BY client_id, lower(vendor_code)
        """), params).fetchall():
            s = slot('WB', cid, vc)
            s['sale'] += float(sale or 0)
            s['cost'] += float(cost or 0)
            s['acquiring'] += float(acq or 0)
            s['commission'] += float(comm_raw or 0) - float(acq or 0)
            s['tac'] += float(tac or 0)
            s['quantities'] += float(qty or 0)

        # OZ: commission хранится отрицательно → ABS.
        for cid, vc, sale, cost, comm, tac, qty in self.session.execute(text("""
            SELECT client_id, lower(vendor_code),
                   SUM(sale), SUM(cost), SUM(ABS(commission)), SUM("TaC"), SUM(quantities)
            FROM oz_main_table_view
            WHERE accrual_date BETWEEN :f AND :t
            GROUP BY client_id, lower(vendor_code)
        """), params).fetchall():
            s = slot('OZON', cid, vc)
            s['sale'] += float(sale or 0)
            s['cost'] += float(cost or 0)
            s['commission'] += float(comm or 0)
            s['tac'] += float(tac or 0)
            s['quantities'] += float(qty or 0)

        # YA: комиссии нет в main; добавим из services ниже.
        for cid, vc, sale, cost, tac, qty in self.session.execute(text("""
            SELECT client_id, lower(vendor_code),
                   SUM(sale), SUM(cost), SUM("TaC"), SUM(quantities)
            FROM ya_main_table_view
            WHERE accrual_date BETWEEN :f AND :t
            GROUP BY client_id, lower(vendor_code)
        """), params).fetchall():
            s = slot('YANDEX', cid, vc)
            s['sale'] += float(sale or 0)
            s['cost'] += float(cost or 0)
            s['tac'] += float(tac or 0)
            s['quantities'] += float(qty or 0)

        # --- services_final per МП — раскладываем по категориям через CASE-WHEN ---
        serv_tables = {
            'WB': ('wb_services_final', 'SUM({c})'),
            'OZON': ('oz_services_final', 'SUM(ABS({c}))'),  # удержания отрицательные → ABS
            'YANDEX': ('ya_services_final', 'SUM({c})'),
        }
        for mp, (table, agg_tmpl) in serv_tables.items():
            cats = category_types[mp]
            select_parts = []
            for cat, types in cats.items():
                in_list = ",".join(f"'{t}'" for t in types)
                inner = f"CASE WHEN lower(type_name) IN ({in_list}) THEN cost ELSE 0 END"
                select_parts.append(f"{agg_tmpl.format(c=inner)} AS {cat}")

            sql = f"""
                SELECT client_id, lower(vendor_code), {', '.join(select_parts)}
                FROM {table}
                WHERE date BETWEEN :f AND :t
                GROUP BY client_id, lower(vendor_code)
            """
            rows = self.session.execute(text(sql), params).fetchall()
            cat_names = list(cats.keys())
            for row in rows:
                cid, vc = row[0], row[1]
                s = slot(mp, cid, vc)
                for i, cat in enumerate(cat_names, start=2):
                    s[cat] += float(row[i] or 0)

        return [
            DataProfit(
                marketplace=mp, client_id=cid, vendor_code=vc,
                sale=s['sale'], cost=s['cost'],
                commission=s['commission'], acquiring=s['acquiring'],
                logistics=s['logistics'], storage=s['storage'],
                advertising=s['advertising'], other=s['other'],
                tac=s['tac'],
                quantities=s['quantities'],
                profit=(s['sale'] - s['cost'] - s['commission'] - s['acquiring']
                        - s['logistics'] - s['storage'] - s['advertising']
                        - s['other'] - s['tac']),
            )
            for (mp, cid, vc), s in agg.items()
        ]

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
                    analytics[key] += "Значительный рост продаж."
                elif 2 > proc_weeks >= 1.3:
                    analytics[key] += "Рост продаж."
                elif 0.7 > proc_weeks >= 0.3:
                    analytics[key] += "Спад продаж."
                elif 0.3 > proc_weeks:
                    analytics[key] += "Значительный спад продаж."

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
