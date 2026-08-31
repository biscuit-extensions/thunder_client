from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import tomllib
from src.thunder_client import setup
from src.thunder_client.extension import ThunderClient


class TestThunderClientExtension:
    def test_setup_and_registration(self, mock_api) -> None:
        ext = setup(mock_api)
        assert "thunder_client" in mock_api.registered_extensions
        assert isinstance(ext, ThunderClient)
        assert "thunder_client.new_request" in mock_api.commands.commands
        assert "thunder_client.send_request" in mock_api.commands.commands

    def test_extension_manifest_contract(self) -> None:
        manifest_path = Path(__file__).parent.parent / "extension.toml"
        assert manifest_path.exists()
        with open(manifest_path, "rb") as f:
            data = tomllib.load(f)
        assert data["extension"]["id"] == "thunder_client"
        assert data["extension"]["author"] == "tomlin7"
        assert data["extension"]["version"] == "0.2.0"
        assert any("requests" in dep.lower() for dep in data["dependencies"]["python"])

    def test_create_request_builder(self, mock_api) -> None:
        ext = ThunderClient(mock_api)
        req = ext.create_request(
            method="post",
            url="https://api.example.com/items",
            headers={"Custom-Header": "Value"},
            body={"name": "Widget", "price": 19.99},
            auth={"type": "bearer", "token": "my-secret-token"},
        )
        assert req["method"] == "POST"
        assert req["url"] == "https://api.example.com/items"
        assert req["headers"]["Authorization"] == "Bearer my-secret-token"
        assert req["headers"]["Content-Type"] == "application/json"
        assert "Widget" in req["body"]

        basic_req = ext.create_request(
            method="get",
            url="https://api.example.com/protected",
            auth={"type": "basic", "username": "admin", "password": "password123"},
        )
        assert basic_req["headers"]["Authorization"].startswith("Basic ")

    def test_variable_interpolation(self, mock_api) -> None:
        ext = ThunderClient(mock_api)
        ext.set_environment_variable("baseUrl", "https://api.example.com")
        ext.set_environment_variable("version", "v2")

        interpolated = ext.interpolate_variables("{{baseUrl}}/{{version}}/users")
        assert interpolated == "https://api.example.com/v2/users"

    def test_execute_request_success(self, mock_api) -> None:
        ext = ThunderClient(mock_api)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.text = '{"status": "success", "id": 42}'
        mock_resp.headers = {"Content-Type": "application/json"}

        req = ext.create_request("get", "https://api.example.com/item/42")

        with patch("requests.request", return_value=mock_resp):
            resp = ext.execute_request(req)
            assert resp["status"] == 200
            assert resp["ok"] is True
            assert resp["is_json"] is True
            assert "success" in resp["formatted_data"]
            assert resp["latency_ms"] >= 0
            assert resp["badge"] == "200 OK"
            assert "Thunder: 200" in ext.statusbar_button.text

    def test_execute_request_http_error(self, mock_api) -> None:
        ext = ThunderClient(mock_api)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.reason = "Not Found"
        mock_resp.text = '{"error": "Item not found"}'
        mock_resp.headers = {"Content-Type": "application/json"}

        req = ext.create_request("get", "https://api.example.com/missing")
        with patch("requests.request", return_value=mock_resp):
            resp = ext.execute_request(req)
            assert resp["status"] == 404
            assert resp["ok"] is False
            assert resp["badge"] == "404 Not Found"
            assert "Thunder: 404" in ext.statusbar_button.text

    def test_format_response_formatting(self, mock_api) -> None:
        ext = ThunderClient(mock_api)
        raw_json = '{"a":1,"b":[2,3]}'
        formatted = ext.format_response(200, raw_json, {"Server": "Mock"}, latency_ms=12.5, reason="OK")
        assert formatted["is_json"] is True
        assert "\n" in formatted["formatted_data"]
        assert formatted["size_bytes"] == len(raw_json.encode("utf-8"))

        raw_plain = "Plain text message"
        plain_formatted = ext.format_response(200, raw_plain, reason="OK")
        assert plain_formatted["is_json"] is False
        assert plain_formatted["formatted_data"] == raw_plain

    def test_collections_management(self, mock_api) -> None:
        ext = ThunderClient(mock_api)
        req1 = ext.create_request("get", "https://api.example.com/1")
        req2 = ext.create_request("post", "https://api.example.com/2", body='{"foo":"bar"}')

        ext.save_to_collection("Users API", req1)
        ext.save_to_collection("Users API", req2)

        cols = ext.list_collections()
        assert "Users API" in cols
        items = ext.get_collection("Users API")
        assert len(items) == 2

        exported = ext.export_collections()
        assert "Users API" in exported

        ext2 = ThunderClient(mock_api)
        success = ext2.import_collections(exported)
        assert success is True
        assert len(ext2.get_collection("Users API")) == 2

    def test_history_tracking(self, mock_api) -> None:
        ext = ThunderClient(mock_api)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.text = "{}"
        mock_resp.headers = {}

        req = ext.create_request("get", "https://api.example.com/test")
        with patch("requests.request", return_value=mock_resp):
            ext.execute_request(req)

        assert len(ext.get_history()) == 1
        ext.clear_history()
        assert len(ext.get_history()) == 0

    def test_app_instance_compatibility(self, app_instance) -> None:
        ext = setup(app_instance.api)
        assert ext is not None
