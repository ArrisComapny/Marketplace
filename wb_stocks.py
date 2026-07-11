# import asyncio
# import logging
#
# import nest_asyncio
#
# from datetime import datetime
#
# from sqlalchemy.exc import OperationalError
#
# from wb_sdk.errors import ClientError
# from wb_sdk.wb_api import WBApi
# from database import WBDbConnection
# from data_classes import DataWBStock
#
# nest_asyncio.apply()
#
# logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
# logger = logging.getLogger(__name__)
#
#
# async def load_cards_maps(api_user: WBApi) -> tuple[dict, dict]:
#     """
#         Строит справочник из карточек товара:
#             nmID  -> (vendorCode, subjectName)
#             chrtID -> techSize
#         Нужен, т.к. новый метод остатков отдаёт только nmId/chrtId без метаданных.
#     """
#     nm_map, chrt_map = {}, {}
#     updated_at, nm_id, limit = None, None, 100
#     while True:
#         answer = await api_user.get_cards_list(updated_at=updated_at, nm_id=nm_id, limit=limit)
#         if not answer or not answer.cards:
#             break
#         for card in answer.cards:
#             nm_map[card.nmID] = (card.vendorCode, card.subjectName)
#             for size in card.sizes:
#                 if size.chrtID is not None:
#                     chrt_map[size.chrtID] = size.techSize
#         if len(answer.cards) < limit:
#             break
#         updated_at, nm_id = answer.cursor.updatedAt, answer.cursor.nmID
#     return nm_map, chrt_map
#
#
# async def get_stocks(db_conn: WBDbConnection, client_id: str, api_key: str) -> None:
#     """
#         Получает остатки на складах WB для кабинета через метод
#         analytics/v1/stocks-report/wb-warehouses (замена устаревшего supplier/stocks).
#         Метаданные (vendor_code/subject/size) подтягиваются из карточек товара.
#
#         Args:
#             db_conn (WBDbConnection): Объект соединения с базой данных.
#             client_id (str): ID кабинета.
#             api_key (str): API KEY кабинета.
#     """
#     list_stocks = []
#     check_list = []
#
#     # Инициализация API-клиента WB
#     api_user = WBApi(api_key=api_key)
#
#     # 1) Справочник карточек: nmID -> (vendor_code, subject), chrtID -> размер
#     nm_map, chrt_map = await load_cards_maps(api_user)
#
#     # 2) Остатки постранично (лимит нового метода: 1 запрос / 20 сек на аккаунт)
#     offset, limit = 0, 1000
#     while True:
#         answer = await api_user.get_stocks_report_wb_warehouses(limit=limit, offset=offset)
#         items = answer.data.items if (answer and answer.data) else []
#         if not items:
#             break
#
#         for item in items:
#             if item.quantity or item.inWayToClient or item.inWayFromClient:
#                 key = (item.nmId, item.chrtId, item.warehouseName)
#                 if key in check_list:
#                     continue
#                 vendor_code, subject = nm_map.get(item.nmId, ('', ''))
#                 list_stocks.append(DataWBStock(date=datetime.today().date(),
#                                                client_id=client_id,
#                                                sku=str(item.nmId),
#                                                vendor_code=vendor_code or '',
#                                                size=chrt_map.get(item.chrtId) or '',
#                                                category='',
#                                                subject=subject or '',
#                                                warehouse=item.warehouseName,
#                                                quantity_warehouse=item.quantity,
#                                                quantity_to_client=item.inWayToClient,
#                                                quantity_from_client=item.inWayFromClient))
#                 check_list.append(key)
#
#         if len(items) < limit:
#             break
#         offset += limit
#         await asyncio.sleep(20)   # держим лимит 1 запрос / 20 сек
#
#     logger.info(f"Количсетво строк: {len(list_stocks)}")
#     db_conn.add_wb_stock_entry(list_stocks=list_stocks)
#
#
# async def main_wb_stock(retries: int = 6) -> None:
#     try:
#         db_conn = WBDbConnection()
#
#         db_conn.start_db()
#
#         clients = db_conn.get_clients(marketplace="WB")
#
#         for client in clients:
#             try:
#                 logger.info(f'Сбор информации о остатках на складах {client.name_company}')
#                 await get_stocks(db_conn=db_conn,
#                                  client_id=client.client_id,
#                                  api_key=client.api_key)
#             except ClientError as e:
#                 logger.error(f'{e}')
#     except OperationalError:
#         logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
#         if retries > 0:
#             await asyncio.sleep(10)
#             await main_wb_stock(retries=retries - 1)
#     except Exception as e:
#         logger.error(f'{e}')
#
# if __name__ == "__main__":
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(main_wb_stock())
#     loop.stop()
