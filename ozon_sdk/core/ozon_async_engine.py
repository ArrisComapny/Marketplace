import asyncio
import aiohttp
import logging

from config import PROXY
from ozon_sdk.errors import ClientError

logger = logging.getLogger(__name__)


class OzonAsyncEngine:

    def __init__(self, client_id: str = '', api_key: str = ''):
        self._base_url = 'https://api-seller.ozon.ru'
        self.__headers = {
            'Client-Id': client_id,
            'Api-Key': api_key
        }

        self.proxy_url = PROXY

    async def get(self, url: str, params: dict) -> dict:
        url = await self._get_url(url)
        response = await self._perform_get_request(url, params)
        return response

    async def post(self, url: str, params: dict) -> dict:
        url = await self._get_url(url)
        response = await self._perform_post_request(url, params)
        return response

    async def _get_url(self, url: str):
        if url.startswith("/"):
            return self._base_url + url
        else:
            return f"{self._base_url}/{url}"

    async def _perform_get_request(self, url, params, retry: int = 6):
        async with await self._get_session() as session:
            while retry != 0:
                try:
                    new_params = {k: v for k, v in params.items() if v is not None}
                    async with session.get(url, params=new_params, ssl=False, timeout=120) as response:
                        if response.status in [404, 403]:
                            raise ClientError
                        if response.status != 200:
                            logger.info(f"Получен ответ от {url} ({response.status})")
                            logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                            await asyncio.sleep(120)
                            retry -= 1
                            continue
                        return await response.json(content_type=None)
                except (aiohttp.ClientConnectionError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Ошибка соединения: {e}")
                    logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                    await asyncio.sleep(120)
                    retry -= 1
                    continue
            raise Exception

    async def _perform_post_request(self, url, params, retry: int = 6):
        async with await self._get_session() as session:
            while retry != 0:
                try:
                    async with session.post(url, json=params, ssl=False, timeout=120) as response:
                        if response.status in [404, 403]:
                            raise ClientError
                        if response.status == 400:
                            r = await response.json()
                            # logger.error(f"400 от {url}: {r}")
                            if r.get('code', 0) == 3:
                                raise ClientError(r.get('message', ''))
                            if 'forbidden' in r.get('error', ''):
                                raise ClientError(r.get('error', ''))
                        if response.status != 200:
                            logger.info(f"Получен ответ от{url} ({response.status})")
                            logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                            await asyncio.sleep(120)
                            retry -= 1
                            continue
                        return await response.json()
                except (aiohttp.ClientConnectionError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Ошибка соединения: {e}")
                    logger.error(f"Попытка повторного запроса. Осталось попыток: {retry - 1}")
                    await asyncio.sleep(120)
                    retry -= 1
                    continue
            raise Exception

    async def _get_session(self):
        session = aiohttp.ClientSession()

        session.headers["Client-Id"] = self.__headers['Client-Id']
        session.headers["Api-Key"] = self.__headers['Api-Key']

        return session


class OzonPerformanceAsyncEngine(OzonAsyncEngine):
    def __init__(self, client_id: str = '', client_secret: str = ''):
        super().__init__()
        self._base_url = 'https://api-performance.ozon.ru'
        self.__headers = {}
        url = '/api/client/token'
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials"
        }
        response = asyncio.run(self.post(url, data))
        token = response.get("access_token")

        self.__headers = {
            'Api-Key': f"Bearer {token}"
        }

    async def _get_session(self):
        session = aiohttp.ClientSession()

        if self.__headers:
            session.headers["Authorization"] = self.__headers['Api-Key']

        return session
