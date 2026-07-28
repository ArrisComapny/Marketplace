import asyncio
import aiohttp
import logging

from config import PROXY
from wb_sdk.errors import ClientError

logger = logging.getLogger(__name__)


class WBAsyncEngine:
    def __init__(self, api_key: str = ''):
        self.__headers = {
            'Authorization': api_key
        }
        self.proxy_url = PROXY

    async def get(self, url: str, json: dict, params: dict, file: bool) -> dict:
        response = await self._perform_get_request(url, file, json, params)
        return response

    async def post(self, url: str, json: dict, params: dict, chat: bool) -> dict:
        response = await self._perform_post_request(url, json, params, chat)
        return response

    async def _perform_get_request(self, url, file: bool, json=None, params=None, retry: int = 6):
        async with await self._get_session(file) as session:
            while retry != 0:
                try:
                    if params:
                        params = {k: v for k, v in params.items() if v is not None}
                    async with session.get(url, json=json, params=params, ssl=False, timeout=180) as response:
                        if response.status == 404:
                            detail = await response.json()
                            raise ClientError(detail.get('detail', 'Отсутствует ответ'))
                        if response.status in [403, 401]:
                            raise ClientError
                        if response.status == 204:
                            return []
                        if response.status not in [200, 201, 204]:
                            logger.info(f"Получен ответ от {url} ({response.status})")
                            logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                            await asyncio.sleep(60)
                            retry -= 1
                            continue
                        if file:
                            content = await response.read()
                            return {'file': content}
                        return await response.json(content_type=None)
                except (aiohttp.ClientConnectionError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Ошибка соединения: {e}")
                    logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                    await asyncio.sleep(60)
                    retry -= 1
                    continue
            raise Exception

    async def _perform_post_request(self, url, json=None, params=None, chat=None, retry: int = 6):
        async with await self._get_session(chat) as session:
            while retry != 0:
                try:
                    async with session.post(url, json=json, params=params, ssl=False, timeout=120) as response:
                        if response.status in [404, 403, 401]:
                            raise ClientError
                        if response.content_type != 'application/json':
                            logger.info(f"Получен ответ от {url} ({response.status}, {response.content_type})")
                            logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                            await asyncio.sleep(60)
                            if response.status == 503:
                                await asyncio.sleep(60)
                            retry -= 1
                            continue
                        if response.status not in [200, 204]:
                            r = await response.json()
                            if r.get('error') == 'некорректные параметры запроса: нет кампаний с корректными интервалами':
                                logger.error(f"Получен ответ от {url} ({response.status}) {r.get('error')}")
                                return None
                            elif r.get('detail') == 'Authorization error':
                                logger.error(f"Получен ответ от {url} ({response.status}) {r.get('detail')}")
                                return None
                            logger.info(f"Получен ответ от {url} ({response.status})")
                            logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                            await asyncio.sleep(60)
                            retry -= 1
                            continue
                        return await response.json()
                except (aiohttp.ClientConnectionError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Ошибка соединения: {e}")
                    logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                    await asyncio.sleep(60)
                    retry -= 1
                    continue
            raise Exception

    async def _get_session(self, file: bool = False, chat: bool = False) -> aiohttp.ClientSession:
        session = aiohttp.ClientSession()

        session.headers["Authorization"] = self.__headers['Authorization']
        session.headers["Accept"] = 'application/json'

        if file:
            session.headers["Accept"] = 'text/csv'

        if chat:
            session.headers["Accept"] = 'multipart/form-data'

        return session
