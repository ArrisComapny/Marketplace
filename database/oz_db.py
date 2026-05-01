import logging

from typing import Type
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert

from .models import *
from data_classes import *
from .db import DbConnection, retry_on_exception

logger = logging.getLogger(__name__)


class OzDbConnection(DbConnection):

    @retry_on_exception()
    def get_oz_performance(self, client_id: str) -> Type[OzPerformance]:
        """
            Получает данные реклаиного кабинета по ID кабинета Ozon.

            Args:
                client_id (str): ID кабинета Ozon.

            Returns:
                Type[OzPerformance]: Данные рекламного кабинета, удовлетворяющих условию фильтрации.
        """
        result = self.session.query(OzPerformance).filter_by(client_id=client_id).first()
        return result

    @retry_on_exception()
    def get_oz_adverts_id(self, client_id: str) -> dict:
        """
            Получает список ID рекламных компаний, отфильтрованных по кабинету и дате активности.

            Args:
                client_id (str): ID кабинета.

            Returns:
                List[str]: Список ID рекламных компаний, удовлетворяющих условию фильтрации.
        """
        result = self.session.query(OzAdverts.id_advert, OzAdverts.field_type).filter_by(client_id=client_id).all()
        return {advert_id: field_type for advert_id, field_type in result}

    @retry_on_exception()
    def get_oz_sku_vendor_code(self, client_id: str) -> dict:
        """
            Получает список SKU товаров, отфильтрованных по кабинету.

            Args:
                client_id (str): ID кабинета.

            Returns:
                dict: словарь {sku: vendor_code}.
        """
        result = self.session.query(OzCardProduct.sku, OzCardProduct.vendor_code).filter_by(client_id=client_id).all()
        return {sku: vendor_code for sku, vendor_code in result}

    @retry_on_exception()
    def add_oz_operation(self, list_operations: list[DataOperation]) -> None:
        """
            Добавление в базу данных записей об операциях с товарами.

            Args:
                list_operations (list[DataOperation]): Список данных об операциях.
        """
        for row in list_operations:
            stmt = insert(OzMain).values(
                client_id=row.client_id,
                accrual_date=row.accrual_date,
                type_of_transaction=row.type_of_transaction,
                vendor_code=row.vendor_code,
                posting_number=row.posting_number,
                delivery_schema=row.delivery_schema,
                sku=row.sku,
                sale=row.sale,
                quantities=row.quantities,
                commission=row.commission,
                bonus=row.bonus
            ).on_conflict_do_update(
                index_elements=['type_of_transaction', 'posting_number', 'sku'],
                set_={'accrual_date': row.accrual_date,
                      'sale': row.sale,
                      'quantities': row.quantities,
                      'commission': row.commission,
                      'bonus': row.bonus}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_adverts(self, client_id: str, adverts_list: list[DataOzAdvert]) -> None:
        """
            Обновление информации о рекламных компаниях.

            Args:
                client_id (str): ID кабинета.
                adverts_list (list[DataOzAdvert]): Список данных о рекламных компаниях.
        """
        advert_types = self.session.query(OzTypeAdvert.field_type).all()
        advert_types = set([advert_type.field_type for advert_type in advert_types])
        for row in adverts_list:
            if row.field_type not in advert_types:
                self.session.add(OzTypeAdvert(field_type=row.field_type, type=row.field_type))
                advert_types.add(row.field_type)
            new = OzAdverts(id_advert=row.id_advert,
                            client_id=client_id,
                            field_type=row.field_type,
                            field_status=row.field_status,
                            name_advert=row.name_advert,
                            create_time=row.create_time,
                            change_time=row.change_time,
                            start_time=row.start_time,
                            end_time=row.end_time)
            self.session.merge(new)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_cards_products(self, list_card_product: list[DataOzProductCard]) -> None:
        """
            Обновление информации о карточках товаров.

            Args:
                list_card_product (list[DataOzProductCard]): Список данных о карточках товаров.
        """
        for row in list_card_product:
            new = OzCardProduct(sku=row.sku,
                                client_id=row.client_id,
                                vendor_code=row.vendor_code,
                                category=row.category,
                                brand=row.brand,
                                link=row.link,
                                price=row.price,
                                discount_price=row.discount_price,
                                created_at=row.created_at)
            self.session.merge(new)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_statistics_card_products(self, list_card_product: list[DataOzStatisticCardProduct]) -> None:
        """
            Добавление в базу данных записей по статистики карточек товаров.

            Args:
                list_card_product (list[DataOzStatisticCardProduct]): Список данных статистики карточек товаров.
        """
        for row in list_card_product:
            card_product = self.session.query(OzCardProduct).filter_by(sku=row.sku).first()
            stmt = insert(OzStatisticCardProduct).values(
                sku=row.sku,
                date=row.date,
                view_search=row.view_search,
                view_card=row.view_card,
                add_to_cart_from_search_count=row.add_to_cart_from_search_count,
                add_to_cart_from_card_count=row.add_to_cart_from_card_count,
                orders_count=row.orders_count,
                orders_sum=row.orders_sum,
                delivered_count=row.delivered_count,
                returns_count=row.returns_count,
                cancel_count=row.cancel_count,
                price=card_product.price,
                discount_price=card_product.discount_price
            ).on_conflict_do_update(
                index_elements=['sku', 'date'],
                set_={'view_search': row.view_search,
                      'view_card': row.view_card,
                      'add_to_cart_from_search_count': row.add_to_cart_from_search_count,
                      'add_to_cart_from_card_count': row.add_to_cart_from_card_count,
                      'orders_count': row.orders_count,
                      'orders_sum': row.orders_sum,
                      'delivered_count': row.delivered_count,
                      'returns_count': row.returns_count,
                      'cancel_count': row.cancel_count}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_statistics_adverts(self, list_statistics_advert: list[DataOzStatisticAdvert]) -> None:
        """
            Добавление в базу данных записей по статистики РК.

            Args:
                list_statistics_advert (list[DataOzStatisticAdvert]): Список данных статистики РК.
        """
        for row in list_statistics_advert:
            stmt = insert(OzStatisticAdvert).values(
                sku=row.sku,
                advert_id=row.advert_id,
                date=row.date,
                views=row.views,
                clicks=row.clicks,
                orders_count=row.orders_count,
                sum_price=row.sum_price,
                sum_cost=row.sum_cost
            ).on_conflict_do_update(
                index_elements=['sku', 'advert_id', 'date'],
                set_={'views': row.views,
                      'clicks': row.clicks,
                      'orders_count': row.orders_count,
                      'sum_price': row.sum_price,
                      'sum_cost': row.sum_cost}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_adverts_daily_budget(self, date: datetime.date,
                                    adverts_daily_budget: list[DataOzAdvertDailyBudget]) -> None:
        """
            Добавление в базу данных записей по бюджету РК.

            Args:
                date (datetime.date): дата актуальная для бюджета.
                adverts_daily_budget (list[DataOzAdvertDailyBudget]): список данных по бюджету РК.
        """
        for row in adverts_daily_budget:
            stmt = insert(OzAdvertDailyBudget).values(
                date=date,
                advert_id=row.advert_id,
                daily_budget=row.daily_budget
            ).on_conflict_do_update(
                index_elements=['date', 'advert_id'],
                set_={'daily_budget': row.daily_budget}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_storage_entry(self, list_storage: list[DataOzStorage]) -> None:
        """
            Добавление в базу данных записей по хранению товаров.

            Args:
                list_storage (list[DataOzStorage]): список данных по хранению товаров.
        """
        for row in list_storage:
            product = self.session.query(OzCardProduct.client_id).filter_by(sku=row.sku).first()
            if product:
                client_id = product[0]
                break
        else:
            logger.error(f"Магазин не найден в БД. Данные не добавлены")
            return
        product_data = self.get_oz_sku_vendor_code(client_id=client_id)
        for row in list_storage:
            stmt = insert(OzStorage).values(
                client_id=client_id,
                date=row.date,
                vendor_code=product_data.get(row.sku, '---UNKNOWN_VENDOR'),
                sku=row.sku,
                cost=row.cost
            ).on_conflict_do_update(
                index_elements=['client_id', 'date', 'sku'],
                set_={'cost': row.cost}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_services_entry(self, client_id: str, list_services: list[DataOzService]) -> None:
        """
            Добавление в базу данных записей по услугам.

            Args:
                client_id (str): ID кабинета.
                list_services (list[DataOzService]): список данных по услугам.
        """
        type_services = set(self.session.query(OzTypeServices.operation_type,
                                               OzTypeServices.service).all())
        product_data = self.get_oz_sku_vendor_code(client_id=client_id)
        for row in list_services:
            if (row.operation_type, row.service or '') not in type_services:
                new_type = OzTypeServices(operation_type=row.operation_type,
                                          service=row.service or '',
                                          type_name='new')
                self.session.add(new_type)
                type_services.add((row.operation_type, row.service or ''))
            stmt = insert(OzServices).values(
                client_id=row.client_id,
                date=row.date,
                operation_type=row.operation_type,
                operation_type_name=row.operation_type_name,
                vendor_code=product_data.get(row.sku) or row.vendor_code or '',
                sku=row.sku or '',
                posting_number=row.posting_number or '',
                service=row.service or '',
                cost=row.cost
            ).on_conflict_do_update(
                index_elements=['client_id',
                                'date',
                                'operation_type',
                                'sku',
                                'posting_number',
                                'service'],
                set_={'cost': row.cost}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_orders(self, list_orders: list[DataOzOrder]) -> None:
        """
            Добавление в базу данных записи о заказах.

            Args:
                list_orders (list[DataOzOrder]): Список данных о заказах.
        """
        for row in list_orders:
            stmt = insert(OzOrders).values(
                client_id=row.client_id,
                order_date=row.order_date,
                sku=row.sku,
                vendor_code=row.vendor_code,
                posting_number=row.posting_number,
                delivery_schema=row.delivery_schema,
                quantities=row.quantities,
                price=row.price
            ).on_conflict_do_update(
                index_elements=['order_date', 'sku', 'posting_number'],
                set_={'vendor_code': row.vendor_code,
                      'quantities': row.quantities,
                      'price': row.price}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_stock_entry(self, list_stocks: list[DataOzStock]) -> None:
        """
            Добавление в базу данных записи о остатках на складах.

            Args:
                list_stocks (list[DataOzStock]): Список данных о остатках на складах.
        """
        for row in list_stocks:
            stmt = insert(OzStock).values(
                date=row.date,
                client_id=row.client_id,
                sku=row.sku,
                vendor_code=row.vendor_code,
                size=row.size,
                quantity=row.quantity,
                reserved=row.reserved
            ).on_conflict_do_nothing(index_elements=['date', 'sku', 'size'])
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_oz_bonus_entry(self, list_bonus: list[DataOzBonus]) -> None:
        """
            Добавление в базу данных записи о бонусах продавца.

            Args:
                list_bonus (list[DataOzBonus]): Список данных о бонусах продавца.
        """
        for row in list_bonus:
            denominator = row.bonus + row.amount + row.bank_coinvestment
            proc = round(row.bonus / denominator, 2) if denominator and abs(denominator) > 1e-6 else 0
            proc = min(max(proc, -10 ** 10 + 1), 10 ** 10 - 1)

            stmt = insert(OzBonus).values(
                date=row.date,
                client_id=row.client_id,
                sku=row.sku,
                vendor_code=row.vendor_code,
                bonus=row.bonus,
                amount=row.amount,
                bank_coinvestment=row.bank_coinvestment,
                proc=proc
            ).on_conflict_do_nothing(index_elements=['date', 'client_id', 'sku', 'vendor_code'])
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")
