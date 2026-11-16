import ast
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/'.github'/'workflows'/'nox-v52-native-onehost-inspect.yml'
AUDIT=ROOT/'nox-control'/'owner_native_audit.py'
PROBE=ROOT/'nox_runpod'/'teacher_mesh'/'v51'/'hf_range_probe.py'

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

audit=load_module('audit_for_v52_path_contract',AUDIT)
manifest=load_module('hf_manifest_for_v52_path_contract',PROBE)

class V52ExactModelPathWorkflowContractTests(unittest.TestCase):
    def test_v52_workflow_reuses_exact_pinned_stat_probe(self):
        text=WORKFLOW.read_text()
        self.assertIn('Native inspect exact DeepSeek paths through existing V52 SSH route',text)
        self.assertIn('from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection',text)
        self.assertIn('inspect.getsource(audit.pinned_model_paths)',text)
        self.assertIn('"PINNED_MODEL_FILES=" + repr(audit.PINNED_MODEL_FILES)',text)
        self.assertIn('connection.REMOTE =',text)
        self.assertIn('connection.probe()',text)
        self.assertIn("print('NATIVE_DEEPSEEK_PATH='+json.dumps(row,separators=(',',':')))",text)
        self.assertIn("print('NATIVE_READ_ONLY_COMPLETE=true')",text)
        self.assertNotIn('python3 -m nox_runpod.teacher_mesh.v52.remote_inspection',text)

    def test_path_probe_is_metadata_only_and_no_follow(self):
        tree=ast.parse(AUDIT.read_text())
        node=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                  and n.name=='pinned_model_paths')
        names={n.id for n in ast.walk(node) if isinstance(n,ast.Name)}
        attrs={n.attr for n in ast.walk(node) if isinstance(n,ast.Attribute)}
        self.assertIn('lstat',names)
        self.assertFalse(attrs & {'read_text','read_bytes','open','unlink','remove','rename','replace'})
        self.assertFalse(names & {'hashlib','unlink','remove'})
        self.assertNotIn('hashlib',attrs)
        self.assertNotIn('sha256(',ast.unparse(node))
        self.assertEqual(len(audit.PINNED_MODEL_FILES),6)

    def test_reported_targets_match_all_six_immutable_manifest_rows(self):
        expected=tuple((row['path'].rsplit('/',1)[-1],row['bytes'],row['sha256'])
                       for row in manifest.PINNED_SOURCES)
        self.assertEqual(audit.PINNED_MODEL_FILES,expected)
        self.assertEqual(audit.MODEL_MANIFEST_REVISION,
                         manifest.PINNED_SOURCES[0]['revision'])
        self.assertEqual(audit.MODEL_ROOT,'/root/nox/models')

    def test_source_route_keeps_stop_and_model_files_untouched(self):
        text=WORKFLOW.read_text()
        start=text.index('Native inspect exact DeepSeek paths through existing V52 SSH route')
        end=text.index('Mandatory temporary SSH key cleanup',start)
        remote_step=text[start:end]
        for forbidden in ('STOP.flag','NOX_STOP','supervisorctl','nvidia-smi',
                          'read_bytes','read_text','hashlib','unlink(','os.remove',
                          'write_text','download','trainer'):
            self.assertNotIn(forbidden,remote_step)
        self.assertIn('if: success()',text)

    def test_source_ci_does_not_dispatch_native_route(self):
        text=WORKFLOW.read_text()
        self.assertIn('source-contract:',text)
        self.assertIn('github.event_name == \'push\' || github.event_name == \'pull_request\'',text)
        self.assertIn('python3 -m unittest -v test_v52_exact_model_path_workflow_contract',text)
        self.assertIn("github.event_name == 'workflow_dispatch'",text)
        self.assertIn("inputs.allow_native == 'YES'",text)

if __name__=='__main__':
    unittest.main()
