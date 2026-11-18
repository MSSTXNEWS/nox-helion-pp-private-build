"""Derive a self-contained readonly inspector; never execute its entry point."""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
BASE_SHA = 'df01f939195a4222e0f7a4ef20eda0770273967901468592a4c49ed69db2bc07'
UI_SHA = '5ba6af82a8fed7732d39fdaddcf403d067c4b4f760cdce09e2e4e179cf9bd24f'
PRIOR = {'run': 44217878336,
         'raw_sha256': '55c37fb7a3d9e1f1b9cff54db8233468647ffc416c07710c86f71eb6cf1d6a52',
         'last_observed_at': 1794966208.4635143}
WORKERS = ((3723162, 175820222), (3723164, 175820222), (3723165, 175820222))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build(base):
    original = base.read_bytes()
    ui = (HERE / 'UI_CURRENT_SOURCE_PROJECTION.py').read_bytes()
    if digest(original) != BASE_SHA or digest(ui) != UI_SHA:
        raise ValueError('HOLD_INSPECTOR_BUILD_INPUT_PIN')
    text = original.decode()

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('HOLD_INSPECTOR_BUILD_CARDINALITY')
        text = text.replace(old, new)

    insertion = (ui.decode() + '\n\nPRE_QA_EVIDENCE = ' + repr(PRIOR)
                 + '\nPRE_QA_WORKER_LIFETIMES = ' + repr(WORKERS) + '\n\n\n')
    replace('class Reader:\n', insertion + 'class Reader:\n')
    replace('            if valid:\n                for row in workers:\n',
            '            if valid:\n'
            '                require({(row["pid"], row["process_starttime"]) for row in workers}\n'
            '                        == set(PRE_QA_WORKER_LIFETIMES), "SAME_PRE_QA_WORKER_LIFETIMES")\n'
            '                for row in workers:\n')
    replace("                    self.guard(); self.source_guard()\n"
            "                    return {'accepted':True,'status':'THREE_WORKERS_NEW_HEALTH_AND_S03_VERIFIED',\n",
            "                    self.guard(); self.source_guard()\n"
            "                    ui_projection = project(self)\n"
            "                    for pid, start in PRE_QA_WORKER_LIFETIMES:\n"
            "                        process = process_identity(pid)\n"
            "                        require(process is not None and process['start_ticks'] == start\n"
            "                                and process['ppid'] == DIRECTOR['pid'], 'POST_UI_WORKER_LIFETIME')\n"
            "                    self.guard()\n"
            "                    return {'accepted':True,'status':'SAME_THREE_PRE_QA_WORKERS_HEARTBEATS_ADVANCED',\n"
            "                        'pre_qa_evidence':PRE_QA_EVIDENCE,\n"
            "                        'same_pre_qa_worker_lifetimes':True,'ui_current_source':ui_projection,\n")
    raw = text.encode()
    compile(raw, 'owner_native_inspect.py', 'exec')
    output = HERE / 'derived/owner_native_inspect.py'
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(raw)
    metadata = {'schema': 'NOX_POST_ORDINARY_READONLY_INSPECTOR_BUILD_V1',
        'base': {'sha256': BASE_SHA, 'bytes': len(original), 'local_source_modified': False},
        'ui_projection': {'sha256': UI_SHA, 'bytes': len(ui), 'embedded_verbatim': True},
        'derived': {'path': 'derived/owner_native_inspect.py', 'sha256': digest(raw), 'bytes': len(raw)},
        'repository_execution_path': 'nox-control/owner_native_inspect.py',
        'pre_qa_evidence': PRIOR, 'fixed_worker_lifetimes': WORKERS,
        'new_read_scope': 'TWO_UI_FILES_AND_FINAL_READONLY_LIFETIME_RECHECK_OF_THE_SAME_THREE_WORKERS',
        'unchanged_scope': 'Reader IO, SH lock, STOP/source/PID guards, two advancing-heartbeat observations, queue/M2 proof, transport output',
        'operator_action': 'inspect', 'operator_modified': False,
        'coordinator_dispatch_after_completed_ordinary_qa': True,
        'actual_UI_visibility_proven': False, 'native_execution_by_builder': 0}
    (HERE / 'POST_QA_INSPECTOR_BUILD.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=HERE.parent /
                        'four_queue_recovery_20261118/delivery/owner_native_inspect.py')
    result = build(parser.parse_args().base)
    print(json.dumps(result['derived']))
