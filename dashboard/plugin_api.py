"""Shared dashboard/desktop namespace glue; discovery owns only its subrouter.

When combining with task UI routes, keep their router and include
``discovery_router`` once. No registration or runtime profile is cached here.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

# The host imports API files as top-level modules, not plugin-package children.
# Load our package with a source-specific name so separate installed copies do
# not borrow each other's code, and relative imports work without sys.path edits.
_root = Path(__file__).resolve().parents[1]
_name = '_alchemy_task_dashboard_' + hashlib.sha256(str(_root).encode()).hexdigest()[:16]
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, _root / '__init__.py', submodule_search_locations=[str(_root)])
    if _spec is None or _spec.loader is None:
        raise ImportError('Cannot load Alchemy Task dashboard package')
    _package = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _package
    try:
        _spec.loader.exec_module(_package)
    except BaseException:
        sys.modules.pop(_name, None)
        raise
from importlib import import_module
from fastapi import APIRouter

discovery_router = import_module(_name + '.dashboard.discovery_api').router
router = APIRouter()
router.include_router(discovery_router)
