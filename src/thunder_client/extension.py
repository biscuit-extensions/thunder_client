from __future__ import annotations

import typing

from biscuit.extensions import Extension

if typing.TYPE_CHECKING:
    from biscuit.api import ExtensionsAPI


class ThunderClient(Extension):
    """Lightweight GUI REST API client with request runner and collections"""

    def __init__(self, api: ExtensionsAPI) -> None:
        super().__init__(api)
        self.api = api
        self.api.logger.info("Thunder Client extension initialised.")

    def __init__(self, api: ExtensionsAPI) -> None:
        super().__init__(api)
        self.api = api
        self.collections: dict[str, list[dict]] = {}
        self.history: list[dict] = []
        self.api.logger.info("Thunder Client extension initialised.")

    def create_request(self, method: str, url: str, headers: dict | None = None, body: str | None = None) -> dict:
        req = {
            "method": method.upper(),
            "url": url,
            "headers": headers or {"Accept": "application/json"},
            "body": body
        }
        self.history.append(req)
        return req

    def save_to_collection(self, collection_name: str, request: dict) -> None:
        if collection_name not in self.collections:
            self.collections[collection_name] = []
        self.collections[collection_name].append(request)

    def format_response(self, status: int, data: str) -> dict:
        return {
            "status": status,
            "ok": 200 <= status < 300,
            "data": data
        }

    def install(self) -> None:
        self.api.logger.info("Thunder Client extension installed.")
