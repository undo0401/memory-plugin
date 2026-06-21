from __future__ import annotations

"""Canonical memory runtime entrypoint.

`runtime_tick.py` remains as the implementation module for compatibility,
but hook loaders should point at this file so naming matches heartbeat.
"""

import importlib.util
import sys
from pathlib import Path

_MODULE_NAME = "hermes_plugins.memory.runtime_tick_impl"


def _impl_path() -> Path:
    return Path(__file__).with_name("runtime_tick.py")


def _load_impl_module():
    existing = sys.modules.get(_MODULE_NAME)
    if existing is not None:
        return existing
    impl_path = _impl_path()
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load memory runtime impl from {impl_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_impl = _load_impl_module()
patch_gateway_runner = _impl.patch_gateway_runner
handle_hook_event = _impl.handle_hook_event

__all__ = ["patch_gateway_runner", "handle_hook_event"]
