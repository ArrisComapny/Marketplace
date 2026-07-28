from .requests import *
from .response import *
from .core import WBAsyncEngine
from .wb_endpoints_list import WBAPIFactory


class WBApi:

    def __init__(self, api_key: str):
        self._engine = WBAsyncEngine(api_key=api_key)
        self._api_factory = WBAPIFactory(self._engine)

        self._supplier_sales_api = self._api_factory.get_api(SupplierSalesResponse)
        self._supplier_orders_api = self._api_factory.get_api(SupplierOrdersResponse)
        self._promotion_adverts_api = self._api_factory.get_api(PromotionAdvertsResponse)
        self._fullstats_api = self._api_factory.get_api(FullstatsResponse)
        self._nm_report_detail_api = self._api_factory.get_api(NMReportDetailResponse)
        self._list_goods_filter_api = self._api_factory.get_api(ListGoodsFilterResponse)
        self._supplier_report_detail_by_period_api = self._api_factory.get_api(SupplierReportDetailByPeriodResponse)
        self._paid_storage_api = self._api_factory.get_api(PaidStorageResponse)
        self._paid_storage_status_api = self._api_factory.get_api(PaidStorageStatusResponse)
        self._paid_storage_download_api = self._api_factory.get_api(PaidStorageDownloadResponse)
        self._analytics_acceptance_report_api = self._api_factory.get_api(AnalyticsAcceptanceReportResponse)
        self._analytics_acceptance_report_download_api = self._api_factory.get_api(
            AnalyticsAcceptanceReportDownloadResponse)
        self._analytics_antifraud_details_api = self._api_factory.get_api(AnalyticsAntifraudDetailsResponse)
        self._mm_report_downloads_api = self._api_factory.get_api(NmReportDownloadsResponse)
        self._nm_report_downloads_file_api = self._api_factory.get_api(NmReportDownloadsFileResponse)
        self._warehouse_remains_api = self._api_factory.get_api(WarehouseRemainsResponse)
        self._warehouse_remains_tasks_status_api = self._api_factory.get_api(WarehouseRemainsTasksStatusResponse)
        self._warehouse_remains_tasks_download_api = self._api_factory.get_api(WarehouseRemainsTasksDownloadResponse)
        self._supplier_stocks_api = self._api_factory.get_api(SupplierStocksResponse)
        self._fbs_orders_api = self._api_factory.get_api(FBSOrdersResponse)
        self._fbs_warehouses_api = self._api_factory.get_api(FBSWarehousesResponse)
        self._fbs_supply_api = self._api_factory.get_api(FBSSupplyResponse)
        self._fbs_stocks_api = self._api_factory.get_api(FBSStocksResponse)
        self._cards_list_api = self._api_factory.get_api(CardsListResponse)
        self._chats_api = self._api_factory.get_api(ChatsResponse)
        self._message_api = self._api_factory.get_api(MessageResponse)
        self._supplies_api = self._api_factory.get_api(SuppliesResponse)
        self._stocks_report_wb_warehouses_api = self._api_factory.get_api(StocksReportWbWarehousesResponse)

    async def get_stocks_report_wb_warehouses(self, limit: int = 1000, offset: int = 0) \
            -> StocksReportWbWarehousesResponse:
        """Остатки на складах WB (новый метод, замена supplier/stocks). Пагинация по offset."""
        request = StocksReportWbWarehousesRequest(limit=limit, offset=offset)
        answer: StocksReportWbWarehousesResponse = await self._stocks_report_wb_warehouses_api.post(body=request)

        return answer

    async def get_supplier_sales(self, date_from: str, flag: int = 0) -> SupplierSalesResponse:
        """
            Продажи. \n
            Дата в формате RFC3339. Можно передать дату или дату со временем.
            Время можно указывать с точностью до секунд или миллисекунд. \n
                Время передаётся в часовом поясе Мск (UTC+3). \n
                Примеры:
                    2019-06-20 \n
                    2019-06-20T23:59:59 \n
                    2019-06-20T00:00:00.12345 \n
                    2017-03-25T00:00:00

            Args:
                date_from (str): Начальная дата отчета.
                flag (int, option): Если параметр flag=0 (или не указан в строке запроса),
                    при вызове API возвращаются данные, у которых значение поля lastChangeDate
                    (дата время обновления информации в сервисе)
                    больше или равно переданному значению параметра dateFrom.
                    При этом количество возвращенных строк данных варьируется в интервале от 0 до примерно 100 000.
                    Если параметр flag=1, то будет выгружена информация обо всех заказах или продажах с датой,
                    равной переданному параметру dateFrom (в данном случае время в дате значения не имеет).
                    При этом количество возвращенных строк данных будет равно количеству всех заказов или продаж,
                    сделанных в указанную дату, переданную в параметре dateFrom. Default to 0.
        """
        request = SupplierSalesRequest(dateFrom=date_from, flag=flag)
        answer: SupplierSalesResponse = await self._supplier_sales_api.get(query=request)

        return answer

    async def get_supplier_orders(self, date_from: str, flag: int = 0) -> SupplierOrdersResponse:
        """
            Заказы. \n
            Дата в формате RFC3339. Можно передать дату или дату со временем.
            Время можно указывать с точностью до секунд или миллисекунд. \n
                Время передаётся в часовом поясе Мск (UTC+3). \n
                Примеры:
                    2019-06-20 \n
                    2019-06-20T23:59:59 \n
                    2019-06-20T00:00:00.12345 \n
                    2017-03-25T00:00:00

            Args:
                date_from (str): Начальная дата отчета.
                flag (int, option): Если параметр flag=0 (или не указан в строке запроса),
                    при вызове API возвращаются данные, у которых значение поля lastChangeDate
                    (дата время обновления информации в сервисе)
                    больше или равно переданному значению параметра dateFrom.
                    При этом количество возвращенных строк данных варьируется в интервале от 0 до примерно 100 000.
                    Если параметр flag=1, то будет выгружена информация обо всех заказах или продажах с датой,
                    равной переданному параметру dateFrom (в данном случае время в дате значения не имеет).
                    При этом количество возвращенных строк данных будет равно количеству всех заказов или продаж,
                    сделанных в указанную дату, переданную в параметре dateFrom. Default to 0.
        """
        request = SupplierOrdersRequest(dateFrom=date_from, flag=flag)
        answer: SupplierOrdersResponse = await self._supplier_orders_api.get(query=request)

        return answer

    async def get_promotion_adverts(
            self,
            ids: list[int] | None = None,
            status: list[int] | None = None,
            type_field: str | None = None
    ) -> PromotionAdvertsResponse:
        """
            Информация о рекламных кампаниях. \n
            Статус кампании:
                -1 - кампания в процессе удаления \n
                4 - готова к запуску \n
                7 - кампания завершена \n
                8 - отказался \n
                9 - идут показы \n
                11 - кампания на паузе
            Тип кампании:
                cpm — за показы
                cpc — за клик

            Args:
                ids (Optional[list[str]]): Список компаний.
                status (Optional[list[int]]): Статус кампании.
                type_field (Optional[str]): Тип кампании.
        """
        if ids is not None:
            ids = ','.join([str(s) for s in ids])
        if status is not None:
            status = ','.join([str(s) for s in status])
        request = PromotionAdvertsRequest(ids=ids, status=status, type=type_field)
        answer: PromotionAdvertsResponse = await self._promotion_adverts_api.get(query=request)

        return answer

    async def get_fullstats(self, company_ids: list[int], begin_date: str, end_date: str) -> FullstatsResponse:
        """
            Возвращает статистику кампаний. \n
            Дата в формате строки YYYY-DD-MM. \n
            Примеры:
                    "2023-10-07" \n
                    "2023-12-06"

            Args:
                company_ids (list[int]): ID кампании, не более 100.
                begin_date (str):Дата начала интервала.
                end_date (str): Дата окончания интервала.
        """
        request = FullstatsRequest(ids=",".join([str(cid) for cid in company_ids]),
                                   beginDate=begin_date, endDate=end_date)
        answer: FullstatsResponse = await self._fullstats_api.get(query=request)

        return answer

    async def get_nm_report_detail(self, date_from: str, date_to: str, brand_names: list[str] = None,
                                   object_ids: list[int] = None, tag_ids: list[int] = None, nm_ids: list[int] = None,
                                   timezone: str = 'Europe/Moscow', field: str = 'openCard', mode: str = 'asc',
                                   page: int = 1) -> NMReportDetailResponse:
        """
            Получение статистики КТ за выбранный период, по nmID/предметам/брендам/тегам. \n
            Поля brand_names, object_ids, tag_ids, nm_ids могут быть пустыми,
            тогда в ответе идут все карточки продавца. \n
            При выборе нескольких полей в ответ приходят данные по карточкам, у которых есть все выбранные поля.
            Работает с пагинацией. \n
            Можно получить отчёт максимум за последний год (365 дней). \n
            Также в данных, где предоставляется информация по предыдущему периоду:
                В previousPeriod данные за такой же период, что и в selectedPeriod.
                Если дата начала previousPeriod раньше, чем год назад от текущей даты, она будет приведена к виду:
                previousPeriod.start = текущая дата - 365 дней.
            Все виды сортировки field:
                openCard — по открытию карточки (переход на страницу товара) \n
                addToCart — по добавлениям в корзину \n
                orders — по кол-ву заказов \n
                avgRubPrice — по средней цене в рублях \n
                ordersSumRub — по сумме заказов в рублях \n
                stockMpQty — по кол-ву остатков маркетплейса шт. \n
                stockWbQty — по кол-ву остатков на складе шт. \n
                cancelSumRub — сумме возвратов в рублях \n
                cancelCount — по кол-ву возвратов \n
                buyoutCount — по кол-ву выкупов \n
                buyoutSumRub — по сумме выкупов

            Args:
                date_from (str): Начало периода.
                date_to (str): Конец периода.
                brand_names (list[str], optional): Название брендов.. Default to None.
                object_ids (list[int], optional): Идентификаторы предмета.. Default to None.
                tag_ids (list[int], optional): Идентификаторы тега.. Default to None.
                nm_ids (list[int], optional): Артикулы WB.. Default to None.
                timezone (str, optional): Временная зона.. Default to 'Europe/Moscow'.
                field (str, optional): Вид сортировки.. Default to 'openCard'.
                mode (str, optional): asc — по возрастанию, desc — по убыванию.. Default to 'asc'.
                page (int, optional): Страница.. Default to 1.
        """
        request = NMReportDetailRequest(brandNames=brand_names,
                                        objectIDs=object_ids,
                                        tagIDs=tag_ids,
                                        nmIDs=nm_ids,
                                        timezone=timezone,
                                        period=NMReportDetailPeriodRequest(begin=date_from,
                                                                           end=date_to),
                                        orderBy=NMReportDetailOrderByRequest(field=field,
                                                                             mode=mode),
                                        page=page)
        answer: NMReportDetailResponse = await self._nm_report_detail_api.post(body=request)

        return answer

    async def get_list_goods_filter(self, limit: int = 10, offset: int = 0, filter_nm_id: int = None) \
            -> ListGoodsFilterResponse:
        """
            Возвращает информацию о товаре по его артикулу.
            Чтобы получить информацию обо всех товарах, оставьте артикул пустым.

            Args:
                limit (int, optional): Сколько элементов вывести на одной странице (пагинация).
                Максимум 1 000 элементов. Default to 10.
                offset (int, optional): Сколько элементов пропустить.. Default to 0.
                filter_nm_id (int, optional): Артикул Wildberries, по которому искать товар.. Default to None.
        """
        request = ListGoodsFilterRequest(limit=limit, offset=offset, filterNmID=filter_nm_id)
        answer: ListGoodsFilterResponse = await self._list_goods_filter_api.get(query=request)

        return answer

    async def get_supplier_report_detail_by_period(self, date_from: str, date_to: str, limit: int = 100000,
                                                   rrdid: int = 0) -> SupplierReportDetailByPeriodResponse:
        request = SupplierReportDetailByPeriodRequest(dateFrom=date_from,
                                                      limit=limit,
                                                      dateTo=date_to,
                                                      rrdid=rrdid)
        answer: SupplierReportDetailByPeriodResponse = await self._supplier_report_detail_by_period_api.get(
            query=request)

        return answer

    async def get_paid_storage(self, date_from: str, date_to: str) -> PaidStorageResponse:
        request = PaidStorageRequest(dateFrom=date_from,
                                     dateTo=date_to)
        answer: PaidStorageResponse = await self._paid_storage_api.get(query=request)

        return answer

    async def get_paid_storage_status(self, task_id: str) -> PaidStorageStatusResponse:
        request = PaidStorageStatusRequest()
        answer: PaidStorageStatusResponse = await self._paid_storage_status_api.get(query=request,
                                                                                    format_dict={'task_id': task_id})

        return answer

    async def get_paid_storage_download(self, task_id: str) -> PaidStorageDownloadResponse:
        request = PaidStorageDownloadRequest()
        answer: PaidStorageDownloadResponse = await self._paid_storage_download_api.get(query=request,
                                                                                        format_dict={
                                                                                            'task_id': task_id})

        return answer

    async def get_analytics_acceptance_report(self, date_from: str, date_to: str) -> AnalyticsAcceptanceReportResponse:
        request = AnalyticsAcceptanceReportRequest(dateFrom=date_from, dateTo=date_to)
        answer: AnalyticsAcceptanceReportResponse = await self._analytics_acceptance_report_api.get(query=request)

        return answer

    async def get_analytics_acceptance_report_download(self, task_id: str) -> AnalyticsAcceptanceReportDownloadResponse:
        request = AnalyticsAcceptanceReportDownloadRequest()
        answer: AnalyticsAcceptanceReportDownloadResponse = await self._analytics_acceptance_report_download_api.get(
            query=request, format_dict={'task_id': task_id})

        return answer

    async def get_analytics_antifraud_details(self, date_from: str = None) -> AnalyticsAntifraudDetailsResponse:
        request = AnalyticsAntifraudDetailsRequest(date=date_from)
        answer: AnalyticsAntifraudDetailsResponse = await self._analytics_antifraud_details_api.get(query=request)

        return answer

    async def get_mm_report_downloads(self,
                                      uuid: str,
                                      start_date: str,
                                      end_date: str,
                                      nm_ids: list[int] = None,
                                      subject_ids: list[int] = None,
                                      brand_names: list[str] = None,
                                      tag_ids: list[int] = None,
                                      timezone: str = 'Europe/Moscow',
                                      aggregation_level: str = 'day',
                                      skip_deleted_nm: bool = False) -> NmReportDownloadsResponse:
        request = NmReportDownloadsRequest(id=uuid,
                                           params=NmReportDownloadsParamsRequest(nmIDs=nm_ids or [],
                                                                                 subjectIDs=subject_ids or [],
                                                                                 brandNames=brand_names or [],
                                                                                 tagIDs=tag_ids or [],
                                                                                 startDate=start_date,
                                                                                 endDate=end_date,
                                                                                 timezone=timezone,
                                                                                 aggregationLevel=aggregation_level,
                                                                                 skipDeletedNm=skip_deleted_nm))
        answer: NmReportDownloadsResponse = await self._mm_report_downloads_api.post(body=request)

        return answer

    async def get_nm_report_downloads_file(self, uuid: str) -> NmReportDownloadsFileResponse:
        request = NmReportDownloadsFileRequest()
        answer: NmReportDownloadsFileResponse = await self._nm_report_downloads_file_api.get(query=request,
                                                                                             file=True,
                                                                                             format_dict={
                                                                                                 'downloadId': uuid})

        return answer

    async def get_warehouse_remains(self,
                                    locale: str = "ru",
                                    group_by_brand: bool = False,
                                    group_by_subject: bool = False,
                                    group_by_sa: bool = False,
                                    group_by_nm: bool = False,
                                    group_by_barcode: bool = False,
                                    group_by_size: bool = False,
                                    filter_pics: int = 0,
                                    filter_volume: int = 0) -> WarehouseRemainsResponse:
        request = WarehouseRemainsRequest(locale=locale,
                                          groupByBrand=str(group_by_brand).lower(),
                                          groupBySubject=str(group_by_subject).lower(),
                                          groupBySa=str(group_by_sa).lower(),
                                          groupByNm=str(group_by_nm).lower(),
                                          groupByBarcode=str(group_by_barcode).lower(),
                                          groupBySize=str(group_by_size).lower(),
                                          filterPics=filter_pics,
                                          filterVolume=filter_volume)

        answer: WarehouseRemainsResponse = await self._warehouse_remains_api.get(query=request)

        return answer

    async def get_warehouse_remains_tasks_status(self, task_id: str) -> WarehouseRemainsTasksStatusResponse:
        request = WarehouseRemainsTasksStatusRequest()
        answer: WarehouseRemainsTasksStatusResponse = await self._warehouse_remains_tasks_status_api.get(
            query=request, format_dict={'task_id': task_id})

        return answer

    async def get_warehouse_remains_tasks_download(self, task_id: str) -> WarehouseRemainsTasksDownloadResponse:
        request = WarehouseRemainsTasksDownloadRequest()
        answer: WarehouseRemainsTasksDownloadResponse = await self._warehouse_remains_tasks_download_api.get(
            query=request, format_dict={'task_id': task_id})

        return answer

    async def get_supplier_stocks(self, date_from: str) -> SupplierStocksResponse:
        request = SupplierStocksRequest(dateFrom=date_from)
        answer: SupplierStocksResponse = await self._supplier_stocks_api.get(query=request)

        return answer

    async def get_fbs_orders(self,
                             date_from: datetime.datetime,
                             date_to: datetime.datetime,
                             limit: int = 1000,
                             next_field: int = 0):
        date_from = int(date_from.replace(tzinfo=datetime.timezone.utc).timestamp())
        date_to = int(date_to.replace(tzinfo=datetime.timezone.utc).timestamp())
        request = FBSOrdersRequest(dateFrom=date_from, dateTo=date_to, limit=limit, next=next_field)
        answer: FBSOrdersResponse = await self._fbs_orders_api.get(query=request)

        return answer

    async def get_fbs_warehouses(self) -> FBSWarehousesResponse:
        request = FBSWarehousesRequest()
        answer: FBSWarehousesResponse = await self._fbs_warehouses_api.get(query=request)

        return answer

    async def get_fbs_supply(self, supply_id) -> FBSSupplyResponse:
        request = FBSSupplyRequest()
        answer: FBSSupplyResponse = await self._fbs_supply_api.get(query=request, format_dict={'supplyId': supply_id})

        return answer

    async def get_fbs_stocks(self, warehouse_id: str, skus: list[str]) -> FBSStocksResponse:
        request = FBSStocksRequest(skus=skus)
        answer: FBSStocksResponse = await self._fbs_stocks_api.post(body=request,
                                                                    format_dict={'warehouseId': warehouse_id})

        return answer

    async def get_cards_list(self,
                             updated_at: str = None,
                             nm_id: int = None,
                             with_photo: int = -1,
                             text_search: str = None,
                             tag_ids: list[int] = None,
                             allowed_categories_only: bool = False,
                             object_ids: list[int] = None,
                             brands: list[str] = None,
                             imt_id: int = None,
                             ascending: bool = False,
                             limit: int = 100,
                             locale: str = 'ru') -> CardsListResponse:
        query = CardsListQueryRequest(locale=locale)
        body = CardsListBodyRequest(settings=CardsListSettingsBodyRequest(
            sort=CardsListSettingsSortBodyRequest(ascending=ascending),
            filter=CardsListSettingsFilterBodyRequest(
                withPhoto=with_photo,
                textSearch=text_search,
                tagIDs=tag_ids,
                allowedCategoriesOnly=allowed_categories_only,
                objectIDs=object_ids,
                brands=brands,
                imtID=imt_id
            ),
            cursor=CardsListSettingsCursorBodyRequest(limit=limit, updatedAt=updated_at, nmID=nm_id)
        ))
        answer: CardsListResponse = await self._cards_list_api.post(body=body, query=query)

        return answer

    async def get_chats(self) -> ChatsResponse:
        query = ChatsRequest()
        answer: ChatsResponse = await self._chats_api.get(query=query)

        return answer

    async def get_message(self, reply_sign: str, message: str, file: list[str] = None) -> MessageResponse:
        body = MessageRequest(replySign=reply_sign, message=message, file=file)
        answer: MessageResponse = await self._message_api.post(body=body, chat=True)

        return answer

    async def get_supplies(self, from_date: str, to_date: str,
                           limit: int = 1000, offset: int = 0, status_ids: list[int] = None) -> SuppliesResponse:
        query = SuppliesQueryRequest(limit=limit, offset=offset)
        body = SuppliesBodyRequest(dates=[SuppliesDatesBodyRequest(from_field=from_date, till=to_date)],
                                   statusIDs=status_ids or [])
        answer: SuppliesResponse = await self._supplies_api.post(body=body, query=query)

        return answer