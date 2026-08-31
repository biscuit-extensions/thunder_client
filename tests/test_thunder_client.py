from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.thunder_client import setup
from src.thunder_client.extension import ThunderClient


class TestThunderClientExtension:
    def test_extension_setup(self, app_instance) -> None:
        setup(app_instance.api)
        ext = ThunderClient(app_instance.api)
        req = ext.create_request("GET", "https://api.github.com/zen")
        assert req["method"] == "GET"
        ext.save_to_collection("GitHub API", req)
        assert len(ext.collections["GitHub API"]) == 1
        resp = ext.format_response(200, "Practicality beats purity.")
        assert resp["ok"] is True
