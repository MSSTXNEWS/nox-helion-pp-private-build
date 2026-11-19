import base64, hashlib, importlib.util, pathlib, tempfile, unittest
from unittest.mock import patch

SOURCE=pathlib.Path(__file__).resolve().parents[1]/'owner_memory_chat_acceptance.py'

class FailureDoesNotRunDependentStages(unittest.TestCase):
    def test_s03_recovery_hold_skips_all_downstream_stages(self):
        spec=importlib.util.spec_from_file_location('a3_acceptance', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        executed=[]
        raw_first=b'def main():\n    return 2\n'
        raw_second=b'raise RuntimeError("MUST_NOT_EVEN_IMPORT_SECOND")\n'
        raw_third=b'raise RuntimeError("MUST_NOT_EVEN_IMPORT_THIRD")\n'
        names=('owner_s03_recover_activate.py','owner_chat_layout_entry.py','owner_browser_qa_entry.py')
        raws=(raw_first,raw_second,raw_third)
        module.STAGES=tuple((n,hashlib.sha256(raw).hexdigest()) for n,raw in zip(names,raws))
        module.BUNDLE={n:base64.b64encode(raw).decode() for n,raw in zip(names,raws)}
        module.emit=lambda kind,data:executed.append((kind,data))
        with tempfile.TemporaryDirectory() as t, patch.object(module,'Path',lambda _:pathlib.Path(t)):
            result=module.main()
        self.assertEqual(result,2)
        self.assertEqual(len([x for x in executed if x[0]=='memory_chat_component_hold']),1)
        self.assertEqual(executed[0][1]['component'],names[0])
        self.assertEqual(executed[0][1]['reason'],'HOLD_ACCEPTANCE_COMPONENT_RESULT')
        self.assertEqual(len(executed),2)
        self.assertEqual(executed[-1][1]['failed'][0]['component'],names[0])

    def test_s03_system_exit_does_not_bypass_receipt_or_run_dependent_stages(self):
        for raw_first in (
            b'def main():\n    raise SystemExit(0)\n',
            b'raise SystemExit(0)\n',
        ):
            with self.subTest(raw_first=raw_first):
                spec=importlib.util.spec_from_file_location('a3_exit_acceptance', SOURCE)
                module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                emitted=[]
                raws=(raw_first, b'raise AssertionError("SECOND_STAGE_MUST_NOT_RUN")\n')
                names=('owner_s03_recover_activate.py','owner_chat_layout_entry.py')
                module.STAGES=tuple((name,hashlib.sha256(raw).hexdigest()) for name,raw in zip(names,raws))
                module.BUNDLE={name:base64.b64encode(raw).decode() for name,raw in zip(names,raws)}
                module.emit=lambda kind,data:emitted.append((kind,data))
                with tempfile.TemporaryDirectory() as t, patch.object(module,'Path',lambda _:pathlib.Path(t)):
                    result=module.main()
                self.assertEqual(result,2)
                self.assertEqual(len(emitted),2)
                self.assertEqual(emitted[0],('memory_chat_component_hold',
                    {'component':names[0], 'reason':'HOLD_ACCEPTANCE_COMPONENT_SYSTEM_EXIT'}))
                self.assertEqual(emitted[1][0],'memory_chat_batch')
                self.assertEqual(emitted[1][1]['failed'],[emitted[0][1]])


    def test_stop_during_final_stage_cannot_claim_success(self):
        spec=importlib.util.spec_from_file_location('a3_stop_acceptance', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as t:
            name='owner_s03_recover_activate.py'
            raw=(
                b'from pathlib import Path\n'
                b'def main():\n'
                + f'    (Path({t!r}) / "STOP").touch()\n'.encode()
                + b'    return 0\n'
            )
            module.STAGES=((name,hashlib.sha256(raw).hexdigest()),)
            module.BUNDLE={name:base64.b64encode(raw).decode()}
            emitted=[]
            module.emit=lambda kind,data:emitted.append((kind,data))
            with patch.object(module,'Path',lambda _:pathlib.Path(t)):
                result=module.main()
        self.assertEqual(result,2)
        self.assertEqual(emitted,[
            ('memory_chat_component_hold',{'component':name,'reason':'HOLD_OWNER_STOP'}),
            ('memory_chat_batch',{
                'failed':[{'component':name,'reason':'HOLD_OWNER_STOP'}],
                'training_started':False,'private_content_exported':False}),
        ])

if __name__=='__main__':unittest.main()
