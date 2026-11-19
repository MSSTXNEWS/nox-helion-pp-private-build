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

if __name__=='__main__':unittest.main()
