from __future__ import annotations

import typing

from .extension import ThunderClient

if typing.TYPE_CHECKING:
    from biscuit.api import ExtensionsAPI


def setup(api: ExtensionsAPI) -> ThunderClient:
    """Entrypoint for Biscuit to load the extension."""
    ext = ThunderClient(api)
    api.register("thunder_client", ext)
    ext.install()
    return ext
