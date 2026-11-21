"""NOX selftools package facade for the current module-level guarded registry.

The active registry has call()/describe()/load_all() rather than the legacy
Registry/ToolError class interface. Importing this package must not crash
unrelated unittest discovery or manufacture an unsafe second tool registry.
"""
import sys

from . import registry as _registry

MODULES = tuple(_registry.MODULES)


def build_registry(audit_path=None):
    """Return the registered, module-level tools API (no parallel scheduler)."""
    if audit_path is not None:
        raise ValueError("set NOX_AUDIT_LOG explicitly before loading tools")
    # The tool modules import 'registry' as a top-level module, so pin that
    # name to the same source object before loading them. Do not steal an
    # unrelated module's registry namespace.
    active = sys.modules.setdefault("registry", _registry)
    if getattr(active, "__file__", None) != getattr(_registry, "__file__", None):
        raise RuntimeError("HOLD_SELFTOOLS_REGISTRY_COLLISION")
    active.load_all()
    return active
