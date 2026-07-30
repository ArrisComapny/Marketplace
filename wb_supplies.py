# import asyncio
# import logging
#
# import nest_asyncio
#
# from datetime import datetime, timedelta, timezone
#
# from sqlalchemy.exc import OperationalError
#
# from wb_sdk.errors import ClientError
# from wb_sdk.wb_api import WBApi
# from database import WBDbConnection
# from data_classes import DataWBSupply, DataWBSupplyDetails, DataWBSupplyGoods
#
# nest_asyncio.apply()
#
# logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
# logger = logging.getLogger(__name__)
#
#
# async def get_supplies(db_conn: WBDbConnection, client_id: str, api_key: str,
#                        from_date: datetime, to_date: datetime) -> None:
#     """
#         Получает список поставок FBW для указанного клиента за определенный период времени.
#
#         Args:
#             db_conn (WBDbConnection): Объект соединения с базой данных.
#             client_id (str): ID кабинета.
#             api_key (str): API KEY кабинета.
#             from_date (datetime): Начальная дата периода (по дате создания поставки).
#             to_date (datetime): Конечная дата периода (по дате создания поставки).
#     """
#     def format_date(date_format: str) -> datetime | None:
#         """Форматирование даты."""
#         if not date_format:
#             return None
#         return datetime.fromisoformat(date_format)
#
#     list_supplies = []
#
#     # Инициализация API-клиента WB
#     api_user = WBApi(api_key=api_key)
#
#     limit = 1000
#     offset = 0
#
#     while True:
#         # Получение списка поставок
#         answer = await api_user.get_supplies(from_date=from_date.date().isoformat(),
#                                              to_date=to_date.date().isoformat(),
#                                              limit=limit,
#                                              offset=offset)
#
#         if not answer or not answer.result:
#             break
#
#         # Обработка полученных результатов
#         for supply in answer.result:
#             list_supplies.append(DataWBSupply(client_id=client_id,
#                                               supply_id=str(supply.supplyID) if supply.supplyID else None,
#                                               preorder_id=str(supply.preorderID),
#                                               phone=supply.phone,
#                                               create_date=format_date(supply.createDate),
#                                               supply_date=format_date(supply.supplyDate),
#                                               fact_date=format_date(supply.factDate),
#                                               updated_date=format_date(supply.updatedDate),
#                                               status_id=supply.statusID,
#                                               box_type_id=supply.boxTypeID,
#                                               is_box_on_pallet=supply.isBoxOnPallet))
#
#         if len(answer.result) < limit:
#             break
#         offset += limit
#
#     logger.info(f"Количество строк: {len(list_supplies)}")
#     db_conn.add_wb_supplies(list_supplies=list_supplies)
#
#
# async def get_supplies_details(db_conn: WBDbConnection, client_id: str, api_key: str) -> None:
#     """
#         Получает детали и товары отгруженных поставок (статусы 4, 5, 6),
#         которые новые или изменились с прошлого сбора.
#
#         Args:
#             db_conn (WBDbConnection): Объект соединения с базой данных.
#             client_id (str): ID кабинета.
#             api_key (str): API KEY кабинета.
#     """
#     def format_date(date_format: str) -> datetime | None:
#         """Форматирование даты."""
#         if not date_format:
#             return None
#         return datetime.fromisoformat(date_format)
#
#     def to_float(value: str) -> float | None:
#         """Числовые коэффициенты приходят строками ('215'), пустая строка — нет значения."""
#         try:
#             return float(value) if value not in (None, '') else None
#         except ValueError:
#             return None
#
#     supply_ids = db_conn.get_wb_supplies_for_details(client_id=client_id)
#     if not supply_ids:
#         logger.info("Нет поставок, требующих обновления деталей")
#         return
#     logger.info(f"Поставок к обновлению деталей: {len(supply_ids)}")
#
#     # Инициализация API-клиента WB
#     api_user = WBApi(api_key=api_key)
#
#     list_details = []
#     list_goods = []
#
#     def flush() -> None:
#         """Промежуточная запись, чтобы не потерять собранное при долгом прогоне."""
#         if list_details:
#             db_conn.add_wb_supplies_details(list_details=list_details)
#             list_details.clear()
#         if list_goods:
#             db_conn.add_wb_supplies_goods(list_goods=list_goods)
#             list_goods.clear()
#
#     for number, supply_id in enumerate(supply_ids, 1):
#         try:
#             # Детали поставки
#             answer = await api_user.get_supply_details(supply_id=int(supply_id))
#             if answer:
#                 list_details.append(DataWBSupplyDetails(
#                     client_id=client_id,
#                     supply_id=supply_id,
#                     warehouse_id=answer.warehouseID,
#                     warehouse_name=answer.warehouseName,
#                     actual_warehouse_id=answer.actualWarehouseID,
#                     actual_warehouse_name=answer.actualWarehouseName,
#                     acceptance_cost=answer.acceptanceCost,
#                     paid_acceptance_coefficient=answer.paidAcceptanceCoefficient,
#                     storage_coef=to_float(answer.storageCoef),
#                     delivery_coef=to_float(answer.deliveryCoef),
#                     reject_reason=answer.rejectReason,
#                     supplier_assign_name=answer.supplierAssignName,
#                     quantity=answer.quantity,
#                     accepted_quantity=answer.acceptedQuantity,
#                     unloading_quantity=answer.unloadingQuantity,
#                     ready_for_sale_quantity=answer.readyForSaleQuantity,
#                     depersonalized_quantity=answer.depersonalizedQuantity,
#                     virtual_type_id=answer.virtualTypeID,
#                     updated_date=format_date(answer.updatedDate)))
#
#             # Товары поставки
#             limit = 1000
#             offset = 0
#             while True:
#                 answer_goods = await api_user.get_supply_goods(supply_id=int(supply_id),
#                                                                limit=limit,
#                                                                offset=offset)
#                 if not answer_goods or not answer_goods.result:
#                     break
#                 for goods in answer_goods.result:
#                     list_goods.append(DataWBSupplyGoods(
#                         client_id=client_id,
#                         supply_id=supply_id,
#                         barcode=goods.barcode,
#                         vendor_code=goods.vendorCode,
#                         sku=str(goods.nmID) if goods.nmID else None,
#                         tech_size=goods.techSize,
#                         color=goods.color,
#                         need_kiz=goods.needKiz,
#                         supplier_box_amount=goods.supplierBoxAmount,
#                         quantity=goods.quantity,
#                         accepted_quantity=goods.acceptedQuantity,
#                         unloading_quantity=goods.unloadingQuantity,
#                         ready_for_sale_quantity=goods.readyForSaleQuantity))
#                 if len(answer_goods.result) < limit:
#                     break
#                 offset += limit
#                 await asyncio.sleep(2)
#         except ClientError as e:
#             logger.error(f"Поставка {supply_id}: {e}")
#
#         if number % 200 == 0:
#             logger.info(f"Обработано поставок: {number} из {len(supply_ids)}")
#             flush()
#
#         # Лимит WB общий на supplies-api (~30 запросов/мин на всё),
#         # на поставку уходит 2 запроса (детали + товары) — держим ~24 запроса/мин
#         await asyncio.sleep(5)
#
#     flush()
#
#
# async def main_wb_supplies(retries: int = 6) -> None:
#     try:
#         db_conn = WBDbConnection()
#
#         db_conn.start_db()
#
#         clients = db_conn.get_clients(marketplace="WB")
#         date_now = datetime.now(tz=timezone(timedelta(hours=3))).replace(hour=0, minute=0, second=0, microsecond=0)
#         from_date = date_now - timedelta(days=30)
#         to_date = date_now + timedelta(days=1) - timedelta(microseconds=1)
#
#         for client in clients:
#             if client.name_company != "TiVi":
#                 continue
#             try:
#                 logger.info(f'Сбор информации о поставках магазина {client.name_company} '
#                             f'за период с {from_date.date().isoformat()} по {to_date.date().isoformat()}')
#                 await get_supplies(db_conn=db_conn,
#                                    client_id=client.client_id,
#                                    api_key=client.api_key,
#                                    from_date=from_date,
#                                    to_date=to_date)
#                 await get_supplies_details(db_conn=db_conn,
#                                            client_id=client.client_id,
#                                            api_key=client.api_key)
#             except ClientError as e:
#                 logger.error(f'{e}')
#     except OperationalError:
#         logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
#         if retries > 0:
#             await asyncio.sleep(10)
#             await main_wb_supplies(retries=retries - 1)
#     except Exception as e:
#         logger.error(f'{e}')
#
#
# if __name__ == "__main__":
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(main_wb_supplies())
#     loop.stop()
