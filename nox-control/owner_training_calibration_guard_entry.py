"""Reuse the exact reviewed priority installer for the separate generic guard."""
import base64
import hashlib
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
LEGACY_SHA='59ea8ac37bdec4c990950aeef9c4ab7283f633cb300ee6384007111efd06d86c'
GUARD_SHA='a6db1e6ec25db95ccf2de976538fb450e65e9dd8ee97990ed757588b2155d27c'
SCHEMA='NOX_OWNER_CALIBRATED_DISK_GUARD_INSTALL_V1'


def transform(raw):
    if hashlib.sha256(raw).hexdigest()!=LEGACY_SHA:raise RuntimeError('HOLD_CALIBRATED_GUARD_INSTALLER_SOURCE')
    text=raw.decode()
    changes={"load('owner_training_disk_guard',GUARD_SHA)":"load('owner_training_calibration_guard',GUARD_SHA)",
             "guard_path=SCRIPTS/'owner_training_disk_guard.py'":"guard_path=SCRIPTS/'owner_training_calibration_guard.py'"}
    for before,after in changes.items():
        if text.count(before)!=1:raise RuntimeError('HOLD_CALIBRATED_GUARD_INSTALLER_ANCHOR')
        text=text.replace(before,after,1)
    compile(text,'<reviewed-generic-priority-installer>','exec');return text


def main(context):
    raw=base64.b64decode(BUNDLE.get('owner_training_disk_guard_entry.py',''),validate=True)
    module=types.ModuleType('_nox_calibrated_priority_installer');sys.modules[module.__name__]=module
    exec(compile(transform(raw),'<reviewed-generic-priority-installer>','exec'),module.__dict__)
    module.BUNDLE=BUNDLE;module.SCHEMA=SCHEMA;module.GUARD_SHA=GUARD_SHA
    return module.main(context)
