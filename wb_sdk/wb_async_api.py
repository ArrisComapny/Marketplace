from typing import Type

from .core import WBAsyncEngine
from .response import BaseResponse


class WBAsyncApi:

    def __init__(self, engine: WBAsyncEngine, url: str, response_type: Type[BaseResponse]):
        self._engine = engine
        self._url = url
        self._response_type = response_type

    async def get(self, body=None, query=None, file: bool = False, format_dict: dict = None):
        if body:
            body = await self.params_to_dict(body)
        if query:
            query = await self.params_to_dict(query)
        url = self._url
        if format_dict:
            url = url.format(**format_dict)
        response = await self._engine.get(url, file=file, json=body, params=query)
        data = await self._parse_response(response)
        return data

    async def post(self, body=None, query=None, format_dict: dict = None):
        if body:
            body = await self.params_to_dict(body)
        if query:
            query = await self.params_to_dict(query)
        url = self._url
        if format_dict:
            url = url.format(**format_dict)
        response = await self._engine.post(url, json=body, params=query)
        data = await self._parse_response(response)
        return data

    @staticmethod
    async def params_to_dict(params: list or dict) -> list or dict:
        if isinstance(params, list):
            parameters = [param.dict(by_alias=True) for param in params]
        else:
            parameters = params.dict(by_alias=True)
        return parameters

    async def _parse_response(self, response: dict or list):
        if response is None:
            return None
        if isinstance(response, list):
            data = await self._parse_response_object({"result": response})
            return data
        else:
            data = await self._parse_response_object(response)
            return data

    async def _parse_response_object(self, response: dict):
        return self._response_type.parse_obj(response)
