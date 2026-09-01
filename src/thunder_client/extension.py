from __future__ import annotations

import base64
import json
import re
import time
import typing
from typing import Any
import urllib.parse

from biscuit.extensions import Extension

if typing.TYPE_CHECKING:
    from biscuit.api import ExtensionsAPI

try:
    import requests
except ImportError:
    requests = None


class ThunderClient(Extension):
    """Production REST API client for Biscuit IDE.

    Provides HTTP request creation, execution, response inspection,
    collections, history, and statusbar metrics.
    """

    def __init__(self, api: ExtensionsAPI) -> None:
        super().__init__(api)
        self.api = api
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self.history: list[dict[str, Any]] = []
        self.environments: dict[str, str] = {}
        self.last_response: dict[str, Any] | None = None
        self.statusbar_button = None

        if hasattr(self.api, "statusbar") and hasattr(self.api.statusbar, "add_button"):
            try:
                self.statusbar_button = self.api.statusbar.add_button(
                    text="Thunder Client",
                    icon="globe",
                    callback=self._on_statusbar_click,
                    description="Thunder Client REST runner",
                )
                if self.statusbar_button:
                    self.statusbar_button.show()
            except Exception as e:
                self.api.logger.warning(f"Thunder Client statusbar button: {e}")

        self._register_commands()
        self.api.logger.info("Thunder Client extension loaded successfully.")

    def _register_commands(self) -> None:
        if not hasattr(self.api, "commands"):
            return
        cmds = {
            "thunder_client.new_request": self.create_request,
            "thunder_client.send_request": self.execute_request,
            "thunder_client.save_request": self.save_to_collection,
            "thunder_client.view_history": self.get_history,
            "thunder_client.clear_history": self.clear_history,
        }
        for name, callback in cmds.items():
            self.api.commands.register_command(name, callback)

    def _on_statusbar_click(self) -> None:
        if self.last_response:
            status = self.last_response.get("status", 0)
            ms = self.last_response.get("latency_ms", 0)
            self.api.logger.info(f"Last HTTP Status: {status} in {ms:.1f}ms")

    def set_environment_variable(self, name: str, value: str) -> None:
        """Store an environment variable for template interpolation."""
        self.environments[name] = str(value)

    def interpolate_variables(self, text: str) -> str:
        """Substitute {{varName}} templates with environment values."""
        if not text or not isinstance(text, str):
            return text

        def replacer(match: re.Match) -> str:
            var_name = match.group(1).strip()
            return self.environments.get(var_name, match.group(0))

        return re.sub(r"\{\{([a-zA-Z0-9_\-\.]+)\}\}", replacer, text)

    def create_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: str | dict[str, Any] | None = None,
        auth: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Construct a structured REST HTTP request."""
        clean_method = method.upper().strip()
        formatted_headers = dict(headers or {})

        if "Accept" not in formatted_headers:
            formatted_headers["Accept"] = "application/json"

        # Apply basic/bearer authentication headers if supplied
        if auth:
            auth_type = auth.get("type", "").lower()
            if auth_type == "bearer" and "token" in auth:
                formatted_headers["Authorization"] = f"Bearer {auth['token']}"
            elif auth_type == "basic" and "username" in auth:
                raw_cred = f"{auth.get('username', '')}:{auth.get('password', '')}"
                encoded_cred = base64.b64encode(raw_cred.encode("utf-8")).decode("utf-8")
                formatted_headers["Authorization"] = f"Basic {encoded_cred}"

        # Body serialization
        body_str: str | None = None
        if body is not None:
            if isinstance(body, (dict, list)):
                body_str = json.dumps(body)
                if "Content-Type" not in formatted_headers:
                    formatted_headers["Content-Type"] = "application/json"
            else:
                body_str = str(body)

        req = {
            "method": clean_method,
            "url": url,
            "headers": formatted_headers,
            "params": params or {},
            "body": body_str,
            "created_at": time.time(),
        }
        return req

    def execute_request(self, request: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        """Execute HTTP request via requests (or fallback urllib) and measure latency."""
        url = self.interpolate_variables(request.get("url", ""))
        method = request.get("method", "GET").upper()
        raw_headers = request.get("headers", {})
        headers = {self.interpolate_variables(k): self.interpolate_variables(v) for k, v in raw_headers.items()}
        params = request.get("params", {})
        raw_body = request.get("body")
        body = self.interpolate_variables(raw_body) if isinstance(raw_body, str) else raw_body

        start_time = time.perf_counter()

        if requests is not None:
            try:
                resp = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    data=body.encode("utf-8") if isinstance(body, str) else body,
                    timeout=timeout,
                )
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                formatted = self.format_response(
                    status=resp.status_code,
                    data=resp.text,
                    headers=dict(resp.headers),
                    latency_ms=latency_ms,
                    reason=resp.reason,
                )
            except requests.RequestException as e:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                formatted = self.format_response(
                    status=0,
                    data=str(e),
                    headers={},
                    latency_ms=latency_ms,
                    reason="Connection Error",
                )
        else:
            # Native fallback using urllib
            import urllib.request
            import urllib.error

            full_url = url
            if params:
                query_string = urllib.parse.urlencode(params)
                delimiter = "&" if "?" in full_url else "?"
                full_url = f"{full_url}{delimiter}{query_string}"

            req_data = body.encode("utf-8") if body else None
            req = urllib.request.Request(full_url, data=req_data, headers=headers, method=method)

            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    res_body = response.read().decode("utf-8", errors="replace")
                    latency_ms = (time.perf_counter() - start_time) * 1000.0
                    formatted = self.format_response(
                        status=response.status,
                        data=res_body,
                        headers=dict(response.headers),
                        latency_ms=latency_ms,
                        reason="OK",
                    )
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                formatted = self.format_response(
                    status=e.code,
                    data=err_body,
                    headers=dict(e.headers) if hasattr(e, "headers") else {},
                    latency_ms=latency_ms,
                    reason=e.reason if hasattr(e, "reason") else "HTTP Error",
                )
            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                formatted = self.format_response(
                    status=0,
                    data=str(e),
                    headers={},
                    latency_ms=latency_ms,
                    reason="Connection Error",
                )

        self.last_response = formatted
        self.history.append({
            "request": request,
            "response": formatted,
            "timestamp": time.time(),
        })

        self.update_statusbar(formatted.get("status", 0), formatted.get("latency_ms", 0.0))
        return formatted

    def format_response(
        self,
        status: int | dict | Any,
        data: str | None = None,
        headers: dict[str, str] | None = None,
        latency_ms: float = 0.0,
        reason: str = "",
    ) -> dict[str, Any]:
        """Format response into structured payload with formatted body and metrics."""
        if isinstance(status, dict):
            resp = status
            status_code = resp.get("status_code", resp.get("status", 200))
            data_val = resp.get("body", resp.get("data", resp.get("text", "")))
            headers_val = resp.get("headers", headers or {})
            latency_val = resp.get("latency_ms", latency_ms)
            reason_val = resp.get("reason", reason)
            return self.format_response(
                status=status_code,
                data=data_val,
                headers=headers_val,
                latency_ms=latency_val,
                reason=reason_val,
            )
        elif hasattr(status, "status_code"):
            resp = status
            status_code = getattr(resp, "status_code", 200)
            data_val = getattr(resp, "text", getattr(resp, "body", ""))
            headers_val = getattr(resp, "headers", headers or {})
            latency_val = getattr(resp, "latency_ms", latency_ms)
            reason_val = getattr(resp, "reason", reason)
            return self.format_response(
                status=status_code,
                data=data_val,
                headers=headers_val,
                latency_ms=latency_val,
                reason=reason_val,
            )

        if data is None:
            data = ""

        formatted_body = data
        is_json = False
        try:
            parsed = json.loads(data)
            formatted_body = json.dumps(parsed, indent=2)
            is_json = True
        except (json.JSONDecodeError, TypeError):
            pass

        size_bytes = len(data.encode("utf-8")) if data else 0
        badge = f"{status} {reason}".strip() if status > 0 else "ERR"

        return {
            "status": status,
            "reason": reason,
            "ok": 200 <= status < 300,
            "data": data,
            "formatted_data": formatted_body,
            "is_json": is_json,
            "headers": headers or {},
            "latency_ms": round(latency_ms, 2),
            "size_bytes": size_bytes,
            "badge": badge,
        }

    def save_to_collection(self, collection_name: str, request: dict[str, Any]) -> None:
        """Store request in a designated collection."""
        if collection_name not in self.collections:
            self.collections[collection_name] = []
        self.collections[collection_name].append(request)
        self.api.logger.info(f"Saved request to collection '{collection_name}'.")

    def get_collection(self, collection_name: str) -> list[dict[str, Any]]:
        """Retrieve all requests in a collection."""
        return list(self.collections.get(collection_name, []))

    def list_collections(self) -> list[str]:
        """List all collection names."""
        return list(self.collections.keys())

    def export_collections(self) -> str:
        """Serialize collections to a JSON string."""
        return json.dumps(self.collections, indent=2)

    def import_collections(self, json_data: str) -> bool:
        """Import collections from a JSON string."""
        try:
            data = json.loads(json_data)
            if isinstance(data, dict):
                for col_name, items in data.items():
                    if isinstance(items, list):
                        if col_name not in self.collections:
                            self.collections[col_name] = []
                        self.collections[col_name].extend(items)
                return True
        except json.JSONDecodeError as e:
            self.api.logger.error(f"Failed to import collections: {e}")
        return False

    def get_history(self) -> list[dict[str, Any]]:
        """Return history of executed requests."""
        return list(self.history)

    def clear_history(self) -> None:
        """Clear execution history."""
        self.history.clear()
        self.api.logger.info("Thunder Client history cleared.")

    def update_statusbar(self, status: int, latency_ms: float) -> None:
        """Update statusbar text with status code badge and duration."""
        if self.statusbar_button:
            if status > 0:
                self.statusbar_button.change_text(f"Thunder: {status} ({latency_ms:.0f}ms)")
            else:
                self.statusbar_button.change_text("Thunder: Err")

    def install(self) -> None:
        """Called upon extension installation."""
        self.api.logger.info("Thunder Client extension installed.")
