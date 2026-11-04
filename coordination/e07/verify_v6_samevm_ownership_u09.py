"""U09: fail-closed original NOX V6 cross-receipt backend identity gate.

Source regressions only: independent Windows E07 10/10 still needs physical proof.
"""
import re

SOURCE = 'ffca9aaedce9d90750dfb212aabcdfd970162150'
SETUP = '722399ee3d7794a7aa38d93d933026e015fd29b0d8a60fd431b0bc494040a6bc'
BUILD = 'NOX-V16-99fce33d002363f6b3e9b9cf'

class Hold(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Hold(reason)

def verify(producer, uia, qwen, stop, pre_e07):
    """PASS covers only consistent receipt claims, NEVER same-VM or release."""
    require(all(type(x) is dict for x in (producer, uia, qwen, stop, pre_e07)),
            'U09_RECEIPT_SCHEMA_HOLD')
    require(producer.get('schema') == 'NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1'
            and producer.get('source_commit_sha1') == SOURCE
            and producer.get('installer_sha256') == SETUP
            and producer.get('installer_bytes') == 169612753
            and producer.get('release_accepted') is False, 'U09_PRODUCER_PIN_HOLD')
    backend = producer.get('python_backend_sha256')
    require(type(backend) is str and re.fullmatch(r'[0-9a-f]{64}', backend),
            'U09_PRODUCER_BACKEND_PIN_HOLD')
    require(uia.get('schema') == 'NOX-E07-FULL-D02-UIA-v1'
            and uia.get('source_sha') == SOURCE and uia.get('setup_sha256') == SETUP
            and uia.get('build_id') == BUILD and uia.get('physical_setup_verified') is True
            and uia.get('five_uia') == 'PASS'
            and type(uia.get('five_primary')) is dict
            and uia['five_primary'].get('actions_invoked') == 5
            and uia['five_primary'].get('status') == 'PASS'
            and uia.get('release_accepted') is False, 'U09_UIA_SETUP_IDENTITY_HOLD')
    require(qwen.get('schema') == 'nox.installed.qwen.e07-diagnostic.v1'
            and qwen.get('installed_backend_sha256') == backend
            and qwen.get('installed_native') == 'LIVE_NONEMPTY_RESPONSE_VERIFIED'
            and qwen.get('native_history_restart') == 'PASS'
            and type(qwen.get('sqlite_history_rows_after_restart')) is int
            and qwen['sqlite_history_rows_after_restart'] >= 2
            and type(qwen.get('installed_native_generated_bytes')) is int
            and qwen['installed_native_generated_bytes'] > 0
            and qwen.get('release_accepted') is False, 'U09_QWEN_SQLITE_BACKEND_HOLD')
    require(stop.get('schema') == 'nox.native.active-stop.physical.v1'
            and stop.get('backend_sha256') == backend
            and stop.get('native_active_stop') == 'PASS'
            and stop.get('native_stop_ack') == 'PASS'
            and stop.get('interrupted_chat_terminal') == 'NATIVE_CHAT_STOP'
            and type(stop.get('nonempty_deltas_before_stop')) is int
            and stop['nonempty_deltas_before_stop'] > 0
            and stop.get('release_accepted') is False, 'U09_STOP_OWNER_BACKEND_HOLD')
    require(pre_e07.get('schema') == 'NOX-V6-U08-ORDERED-QWEN-THEN-E07-v1'
            and pre_e07.get('source_sha') == SOURCE
            and pre_e07.get('setup_sha256') == SETUP
            and pre_e07.get('build_id') == BUILD
            and pre_e07.get('official_conservative_uninstall') == 'PASS'
            and pre_e07.get('install_root_absent') is True
            and pre_e07.get('prior_rollback_slots_absent') is True
            and pre_e07.get('original_native_data_sha256_unchanged') is True
            and pre_e07.get('release_accepted') is False, 'U09_NOLOSS_IDENTITY_HOLD')
    return {'source_sha': SOURCE, 'setup_sha256': SETUP, 'build_id': BUILD,
            'backend_sha256': backend, 'receipt_identity_chain': 'PASS',
            'same_windows_vm_proven_from_json': False,
            'independent_visual_e07': 'HOLD', 'independent_e07_10_10': 'HOLD',
            'release_accepted': False}
