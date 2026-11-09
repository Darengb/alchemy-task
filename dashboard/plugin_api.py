"""Backend for the Alchemy Task UI in the web dashboard and the desktop app (mounted at /api/plugins/alchemy-task).

The host imports this file as a top-level module, not as part of the plugin package. Load our package under
a source-specific name so separate installed copies never borrow each other's code and relative imports work
without sys.path edits. Each router lives in its own module: task routes, settings routes, and the discovery
routes (owned by the discovery backend).
"""
import hashlib
import importlib.util
import sys
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter

_root = Path(__file__).resolve().parents[1]
_name = "_alchemy_task_dashboard_" + hashlib.sha256(str(_root).encode()).hexdigest()[:16]
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, _root / "__init__.py", submodule_search_locations=[str(_root)])
    _package = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _package
    try:
        _spec.loader.exec_module(_package)
    except BaseException:
        sys.modules.pop(_name, None)
        raise

router = APIRouter()
router.include_router(import_module(_name + ".dashboard.tasks_api").router)
router.include_router(import_module(_name + ".dashboard.settings_api").router)
if (Path(__file__).parent / "discovery_api.py").exists():
    router.include_router(import_module(_name + ".dashboard.discovery_api").router)
