import logging

from datetime import date

from sqlalchemy import or_, text, select, update
from sqlalchemy.dialects.postgresql import insert

from .models import *
from data_classes import *
from .db import DbConnection, retry_on_exception

logger = logging.getLogger(__name__)


class WBDbConnection(DbConnection):
    @retry_on_exception()
    def get_wb_negative(self, client_id: str) -> WBNegative:
        client = self.session.query(WBNegative).filter_by(client_id=client_id).first()
        return client

    @retry_on_exception()
    def get_wb_adverts_id(self, client_id: str, from_date: datetime.date) -> dict:
        """
            Получает список рекламных компаний, отфильтрованных по кабинету и дате активности.

            Args:
                client_id (str): ID кабинета.
                from_date (date): Дата активности.

            Returns:
                List[str]: Список рекламных компаний, удовлетворяющих условию фильтрации.
        """
        result = self.session.query(WBAdverts.id_advert,
                                    WBAdverts.create_time,
                                    WBAdverts.end_time).filter_by(client_id=client_id).filter(
            or_(WBAdverts.id_status == 9,
                WBAdverts.change_time >= from_date)
        ).all()
        return {int(advert_id): (create_time, end_time) for (advert_id, create_time, end_time) in result}

    @retry_on_exception()
    def get_wb_sku_vendor_code(self, client_id: str, new: bool = True) -> dict:
        """
            Получает список SKU товаров, отфильтрованных по кабинету.

            Args:
                client_id (str): ID кабинета.
                new (bool): добавлять ли new в список.

            Returns:
                dict: словарь {sku: vendor_code}.
        """
        excluded = ('other_trash',) if new else ('other_trash', 'new')
        query = text("""
            SELECT wcp.sku, lower(wcp.vendor_code)
            FROM wb_card_product wcp 
            LEFT JOIN ip_vendor_code ivc ON ivc.vendor_code = lower(wcp.vendor_code)
            WHERE ivc."group" NOT IN :excluded
              AND wcp.client_id = :client_id
        """)
        result = self.session.execute(
            query, {"client_id": client_id, "excluded": excluded}
        ).fetchall()
        return {sku: vendor_code for sku, vendor_code in result}

    @retry_on_exception()
    def get_wb_card_vendor_map(self, client_id: str) -> dict:
        """
            Словарь {sku: vendor_code} по карточкам конкретного кабинета.
            vendor_code берётся как есть (оригинальный регистр). Для фолбэка остатков.
        """
        result = self.session.query(WBCardProduct.sku, WBCardProduct.vendor_code) \
            .filter(WBCardProduct.client_id == client_id).all()
        return {sku: vendor_code for sku, vendor_code in result}

    @retry_on_exception()
    def get_wb_stat_card_google(self) -> list:
        """
            Получает данные из wb_stat_card_google.

            Returns:
                List[tuple]: Список данных по статистики карточек.
        """
        query = text("SELECT * FROM wb_stat_card_google;")
        result = self.session.execute(query).fetchall()
        return result

    @retry_on_exception()
    def get_wb_stat_advert_google(self) -> list:
        """
            Получает данные из wb_stat_advert_google.

            Returns:
                List[tuple]: Список данных по статистики РК.
        """
        query = text("SELECT * FROM wb_stat_advert_google;")
        result = self.session.execute(query).fetchall()
        return result

    @retry_on_exception()
    def get_wb_stocks_google(self) -> list:
        """
            Получает данные из wb_stocks_google.

            Returns:
                List[tuple]: Список данных по остаткам на складах.
        """
        query = text("SELECT * FROM wb_stocks_google;")
        result = self.session.execute(query).fetchall()
        return result

    @retry_on_exception()
    def get_wb_stocks_ratio(self) -> list:
        """
            Получает данные из wb_stocks_ratio.

            Returns:
                List[tuple]: Список данных по остаткам на складах.
        """
        query = text("SELECT * FROM wb_stocks_ratio;")
        result = self.session.execute(query).fetchall()
        return result

    @retry_on_exception()
    def get_fbs_supplies(self, client_id: str) -> list:
        """
            Получает незакрытые поставки из wb_fbs_orders

            Returns:
                List[str]: Список поставок.
        """
        result = (
            self.session.query(WBOrderFBS.supply_id)
            .distinct()
            .outerjoin(WBSupplyFBS, WBOrderFBS.supply_id == WBSupplyFBS.supply_id)
            .filter(or_(WBSupplyFBS.done.is_(None), WBSupplyFBS.done.is_(False)),
                    WBOrderFBS.supply_id != '',
                    WBOrderFBS.client_id == client_id)
            .all()
        )
        return [row[0] for row in result]

    # @retry_on_exception()
    # def get_fbs_warehouses(self, client_id: str) -> list[str]:
    #     """
    #         Получаем список складов FBS по клиенту.
    #
    #         Returns:
    #             list: список складов.
    #     """
    #     result = (
    #         self.session.query(WBWarehouseFBS.warehouse_id)
    #         .filter(~WBWarehouseFBS.name.ilike('%DBS%'),
    #                 WBWarehouseFBS.client_id == client_id)
    #         .all()
    #     )
    #     return [row[0] for row in result]
    #
    # @retry_on_exception()
    # def get_fbs_barcodes(self, client_id: str) -> dict:
    #     """
    #         Получаем словарь складов со списком баркодов по клиенту.
    #
    #         Returns:
    #             dict: словарь с данными.
    #     """
    #     data = {}
    #     stmt = select(WBOrderFBS.warehouse_id, WBOrderFBS.vendor_code, func.unnest(WBOrderFBS.barcodes).label('barcode')) \
    #         .filter(WBOrderFBS.client_id == client_id).distinct()
    #     result = self.session.execute(stmt).all()
    #     for warehouse_id, vendor_code, barcode in result:
    #         data.setdefault(warehouse_id, [])
    #         data[warehouse_id].append((barcode, vendor_code))
    #     return data

    @retry_on_exception()
    def add_wb_operation(self, list_operations: list[DataOperation]) -> None:
        """
            Добавление в базу данных записи об операциях с товарами.

            Args:
                list_operations (list[DataOperation]): Список данных об операциях.
        """
        for row in list_operations:
            stmt = insert(WBMain).values(
                client_id=row.client_id,
                accrual_date=row.accrual_date,
                type_of_transaction=row.type_of_transaction,
                vendor_code=row.vendor_code,
                posting_number=row.posting_number,
                delivery_schema=row.delivery_schema,
                sku=row.sku,
                sale=row.sale,
                quantities=row.quantities,
                commission=row.commission
            ).on_conflict_do_update(
                index_elements=['accrual_date', 'type_of_transaction', 'posting_number', 'sku'],
                set_={'sale': row.sale,
                      'quantities': row.quantities,
                      'commission': row.commission}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_adverts(self, client_id: str, adverts_list: list[DataWBAdvert]) -> None:
        """
            Обновление информации о рекламных компаниях.

            Args:
                client_id (str): ID кабинета.
                adverts_list (list[DataWBAdvert]): Список данных о рекламных компаниях.
        """
        for row in adverts_list:
            new = WBAdverts(id_advert=row.id_advert,
                            client_id=client_id,
                            id_type=row.id_type,
                            id_status=row.id_status,
                            name_advert=row.name_advert,
                            create_time=row.create_time,
                            change_time=row.change_time,
                            start_time=row.start_time,
                            end_time=row.end_time)
            self.session.merge(new)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_cards_products(self, list_card_product: list[DataWBCardProduct]) -> None:
        """
            Обновление информации о карточках товаров.

            Args:
                list_card_product (list[DataWBCardProduct]): Список данных о карточках товаров.
        """
        self.session.execute(update(WBCardProduct)
                             .where(WBCardProduct.client_id == list_card_product[0].client_id).values(is_work=False))

        for row in list_card_product:
            new = WBCardProduct(sku=row.sku,
                                client_id=row.client_id,
                                vendor_code=row.vendor_code,
                                link=row.link,
                                price=row.price,
                                discount_price=row.discount_price,
                                is_work=True)

            self.session.merge(new)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_adverts_statistics(self, client_id: str,
                                  product_advertising_campaign: list[DataWBStatisticAdvert],
                                  start_date: date, end_date: date) -> None:
        """
            Заменяет в базе данных записи статистики рекламных компаний.

            Args:
                client_id (str): ID кабинета.
                product_advertising_campaign (list[DataWBStatisticAdvert]): Список данных статистики рекламных компаний.
                start_date (date): Начальная дата записей.
                end_date (date): Конченая дата записей.
        """

        subquery = self.session.query(WBStatisticAdvert.id).join(
            WBAdverts,
            WBStatisticAdvert.advert_id == WBAdverts.id_advert
        ).filter(
            WBStatisticAdvert.date >= start_date,
            WBStatisticAdvert.date <= end_date,
            WBAdverts.client_id == client_id
        ).with_entities(WBStatisticAdvert.id).subquery()
        self.session.query(WBStatisticAdvert).filter(WBStatisticAdvert.id.in_(select(subquery))).delete(
            synchronize_session=False)
        self.session.commit()

        skus = self.get_wb_sku_vendor_code(client_id=client_id)
        for row in product_advertising_campaign:
            if row.sku in skus:
                stmt = insert(WBStatisticAdvert).values(
                    sku=row.sku,
                    advert_id=row.advert_id,
                    date=row.date,
                    views=row.views,
                    clicks=row.clicks,
                    atbs=row.atbs,
                    orders_count=row.orders_count,
                    shks=row.shks,
                    sum_price=row.sum_price,
                    sum_cost=row.sum_cost,
                    appType=row.app_type,
                    client_id=client_id
                ).on_conflict_do_update(
                    index_elements=['sku', 'advert_id', 'date', 'appType'],
                    set_={'views': row.views,
                          'clicks': row.clicks,
                          'atbs': row.atbs,
                          'orders_count': row.orders_count,
                          'shks': row.shks,
                          'sum_price': row.atbs,
                          'sum_cost': row.sum_cost,
                          'client_id': client_id}
                )
                self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_cards_products_statistics(self, client_id: str,
                                         list_card_product: list[DataWBStatisticCardProduct]) -> None:
        """
            Добавление в базу данных записи статистики карточек товаров.

            Args:
                client_id (str): ID кабинета.
                list_card_product (list[DataWBStatisticCardProduct]): Список данных статистики карточек товаров.
        """
        skus = self.get_wb_sku_vendor_code(client_id=client_id)
        for row in list_card_product:
            if row.sku not in skus:
                continue
            card_product = self.session.query(WBCardProduct).filter_by(sku=row.sku).first()
            price = card_product.price
            discount_price = card_product.discount_price
            stmt = insert(WBStatisticCardProduct).values(
                sku=row.sku,
                date=row.date,
                open_card_count=row.open_card_count,
                add_to_cart_count=row.add_to_cart_count,
                orders_count=row.orders_count,
                buyouts_count=row.buyouts_count,
                cancel_count=row.cancel_count,
                orders_sum=row.orders_sum,
                price=price,
                discount_price=discount_price,
                client_id=client_id
            ).on_conflict_do_update(
                index_elements=['sku', 'date', 'client_id'],
                set_={'open_card_count': row.open_card_count,
                      'add_to_cart_count': row.add_to_cart_count,
                      'orders_count': row.orders_count,
                      'buyouts_count': row.buyouts_count,
                      'cancel_count': row.cancel_count,
                      'orders_sum': row.orders_sum}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_report_entry(self, client_id: str, start_date: date, list_report: list[DataWBReport]) -> None:
        self.session.query(WBReport).filter(WBReport.operation_date >= start_date,
                                            WBReport.client_id == client_id).delete(synchronize_session=False)
        self.session.commit()
        type_services = set(self.session.query(WBTypeServices.operation_type,
                                               WBTypeServices.service).all())
        for row in list_report:
            match_found = any(
                row.supplier_oper_name == existing_type[0] and (
                        (existing_type[1] is None and row.bonus_type_name is None) or
                        (existing_type[1] is not None and row.bonus_type_name is not None
                         and row.bonus_type_name.startswith(existing_type[1]))
                )
                for existing_type in type_services
            )
            if not match_found:
                new_type = WBTypeServices(operation_type=row.supplier_oper_name,
                                          service=row.bonus_type_name,
                                          type_name='new')
                self.session.add(new_type)
                type_services.add((row.supplier_oper_name, row.bonus_type_name))

            new = WBReport(client_id=client_id,
                           realizationreport_id=row.realizationreport_id,
                           gi_id=row.gi_id,
                           subject_name=row.subject_name,
                           sku=row.sku,
                           brand=row.brand,
                           vendor_code=row.vendor_code,
                           size=row.size,
                           barcode=row.barcode,
                           doc_type_name=row.doc_type_name,
                           quantity=row.quantity,
                           retail_price=row.retail_price,
                           retail_amount=row.retail_amount,
                           sale_percent=row.sale_percent,
                           commission_percent=row.commission_percent,
                           office_name=row.office_name,
                           supplier_oper_name=row.supplier_oper_name,
                           order_date=row.order_date,
                           sale_date=row.sale_date,
                           operation_date=row.operation_date,
                           shk_id=row.shk_id,
                           retail_price_withdisc_rub=row.retail_price_withdisc_rub,
                           delivery_amount=row.delivery_amount,
                           return_amount=row.return_amount,
                           delivery_rub=row.delivery_rub,
                           gi_box_type_name=row.gi_box_type_name,
                           product_discount_for_report=row.product_discount_for_report,
                           supplier_promo=row.supplier_promo,
                           order_id=row.order_id,
                           ppvz_spp_prc=row.ppvz_spp_prc,
                           ppvz_kvw_prc_base=row.ppvz_kvw_prc_base,
                           ppvz_kvw_prc=row.ppvz_kvw_prc,
                           sup_rating_prc_up=row.sup_rating_prc_up,
                           is_kgvp_v2=row.is_kgvp_v2,
                           ppvz_sales_commission=row.ppvz_sales_commission,
                           ppvz_for_pay=row.ppvz_for_pay,
                           ppvz_reward=row.ppvz_reward,
                           acquiring_fee=row.acquiring_fee,
                           acquiring_bank=row.acquiring_bank,
                           ppvz_vw=row.ppvz_vw,
                           ppvz_vw_nds=row.ppvz_vw_nds,
                           ppvz_office_id=row.ppvz_office_id,
                           ppvz_office_name=row.ppvz_office_name,
                           ppvz_supplier_id=row.ppvz_supplier_id,
                           ppvz_supplier_name=row.ppvz_supplier_name,
                           ppvz_inn=row.ppvz_inn,
                           declaration_number=row.declaration_number,
                           bonus_type_name=row.bonus_type_name,
                           sticker_id=row.sticker_id,
                           site_country=row.site_country,
                           penalty=row.penalty,
                           additional_payment=row.additional_payment,
                           rebill_logistic_cost=row.rebill_logistic_cost,
                           rebill_logistic_org=row.rebill_logistic_org,
                           kiz=row.kiz,
                           storage_fee=row.storage_fee,
                           deduction=row.deduction,
                           acceptance=row.acceptance,
                           posting_number=row.posting_number)
            self.session.add(new)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_storage_entry(self, list_storage: list[DataWBStorage]) -> None:
        """
            Добавление в базу данных записи о хранении.

            Args:
                list_storage (list[DataWBStorage]): Список данных о заказах.
        """
        for row in list_storage:
            stmt = insert(WBStorage).values(
                client_id=row.client_id,
                date=row.date,
                vendor_code=row.vendor_code,
                sku=row.sku,
                calc_type=row.calc_type,
                cost=row.cost
            ).on_conflict_do_update(
                index_elements=['date', 'sku', 'calc_type'],
                set_={'cost': row.cost}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_orders(self, list_orders: list[DataWBOrder]) -> None:
        """
            Добавление в базу данных записи о заказах.

            Args:
                list_orders (list[DataWBOrder]): Список данных о заказах.
        """
        for row in list_orders:
            stmt = insert(WBOrders).values(
                client_id=row.client_id,
                order_date=row.order_date,
                sku=row.sku,
                vendor_code=row.vendor_code,
                posting_number=row.posting_number,
                category=row.category,
                subject=row.subject,
                price=row.price,
                is_cancel=row.is_cancel,
                cancel_date=row.cancel_date,
                warehouse=row.warehouse,
                warehouse_type=row.warehouse_type,
                country=row.country,
                oblast=row.oblast,
                region=row.region
            ).on_conflict_do_update(
                index_elements=['order_date', 'sku', 'posting_number'],
                set_={'vendor_code': row.vendor_code,
                      'category': row.category,
                      'subject': row.subject,
                      'price': row.price,
                      'is_cancel': row.is_cancel,
                      'cancel_date': row.cancel_date,
                      'warehouse': row.warehouse,
                      'warehouse_type': row.warehouse_type,
                      'country': row.country,
                      'oblast': row.oblast,
                      'region': row.region}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_acceptance_entry(self, client_id: str, list_acceptance: list[DataWBAcceptance]) -> None:
        """
            Добавление в базу данных записи о приёмке.

            Args:
                client_id (str): ID кабинета.
                list_acceptance (list[DataWBAcceptance]): Список данных о приёмке.
        """
        skus = self.get_wb_sku_vendor_code(client_id=client_id)
        for row in list_acceptance:
            stmt = insert(WBAcceptance).values(
                client_id=row.client_id,
                date=row.date,
                sku=row.sku,
                vendor_code=skus.get(row.sku) or '---unknown_vendor',
                cost=row.cost
            ).on_conflict_do_update(
                index_elements=['date', 'sku'],
                set_={'cost': row.cost}
            )
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_stock_entry(self, list_stocks: list[DataWBStock]) -> None:
        """
            Добавление в базу данных записи о остатках на складах.

            Args:
                list_stocks (list[DataWBStock]): Список данных о остатках на складах.
        """
        for row in list_stocks:
            stmt = insert(WBStock).values(
                date=row.date,
                client_id=row.client_id,
                sku=row.sku,
                vendor_code=row.vendor_code,
                size=row.size,
                category=row.category,
                subject=row.subject,
                warehouse=row.warehouse,
                quantity_warehouse=row.quantity_warehouse,
                quantity_to_client=row.quantity_to_client,
                quantity_from_client=row.quantity_from_client
            ).on_conflict_do_nothing(index_elements=['client_id', 'date', 'sku', 'warehouse', 'size'])
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_fbs_orders(self, list_orders: list[DataWBOrderFBS]) -> None:
        """
            Добавление в базу данных записи о заказах на FBS.

            Args:
                list_orders (list[DataWBOrderFBS]): Список данных о заказах FBS.
        """
        for row in list_orders:
            stmt = insert(WBOrderFBS).values(
                supply_id=row.supply_id,
                client_id=row.client_id,
                warehouse_id=row.warehouse_id,
                order_date=row.order_date,
                posting_number=row.posting_number,
                vendor_code=row.vendor_code,
                sku=row.sku,
                barcodes=row.barcodes
            ).on_conflict_do_nothing(index_elements=['warehouse_id', 'posting_number'])
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_fbs_warehouses(self, list_warehouses: list[DataWBWarehouseFBS]) -> None:
        """
            Добавление и обновление в базе данных записей о складах FBS.

            Args:
                list_warehouses (list[DataWBWarehouseFBS]): Список данных о складах FBS.
        """
        for row in list_warehouses:
            new = WBWarehouseFBS(warehouse_id=row.warehouse_id,
                                 client_id=row.client_id,
                                 name=row.name,
                                 office_id=row.office_id,
                                 cargo_type=row.cargo_type,
                                 delivery_type=row.delivery_type)
            self.session.merge(new)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_fbs_supplies(self, list_supplies: list[DataWBSupplyFBS]) -> None:
        """
            Добавление и обновление в базе данных записей о поставках FBS.

            Args:
                list_supplies (list[DataWBSupplyFBS]): Список данных о поставках FBS.
        """
        for row in list_supplies:
            new = WBSupplyFBS(supply_id=row.supply_id,
                              client_id=row.client_id,
                              done=row.done,
                              created_at=row.created_at,
                              closed_at=row.closed_at,
                              scan_dt=row.scan_dt,
                              name=row.name,
                              cargo_type=row.cargo_type)
            self.session.merge(new)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")

    @retry_on_exception()
    def add_wb_fbs_stocks(self, list_stocks: list[DataWBStockFBS]) -> None:
        """
            Добавление данных об остатках на складах FBS.

            Args:
                list_stocks (list[DataWBStockFBS]): Список данных о поставках FBS.
        """
        for row in list_stocks:
            stmt = insert(WBStockFBS).values(
                client_id=row.client_id,
                warehouse_id=row.warehouse_id,
                barcode=row.barcode,
                vendor_code=row.vendor_code,
                date=row.date,
                count=row.count
            ).on_conflict_do_nothing(index_elements=['client_id', 'warehouse_id', 'barcode', 'date'])
            self.session.execute(stmt)
        self.session.commit()
        logger.info(f"Успешное добавление в базу")
