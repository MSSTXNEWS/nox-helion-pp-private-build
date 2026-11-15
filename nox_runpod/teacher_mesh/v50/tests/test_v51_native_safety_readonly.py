"""V51 source-only regression of the ACTUAL embedded native read-only functions."""
import ast
import re
import tempfile
import unittest
from pathlib import Path
from nox_runpod.teacher_mesh.v51.ephemeral_ssh_probe import REMOTE

code=REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
tree=ast.parse(code)
nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in {'gpu_pid_map','cgroup_oom_pair'}]
assert len(nodes)==2
context={'re':re}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<v51-native-functions>','exec'),context)

class ReadOnlySafety(unittest.TestCase):
    def test_real_gpu_uuid_join_is_pid_evidence_not_owner_lease(self):
        a='GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        b='GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        def call(args):
            return (0,'0, '+a+'\n1, '+b+'\n') if '--query-gpu=index,uuid' in args else (0,b+', 123, 22000\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'123';path.mkdir();(path/'comm').write_text('python')
            out=context['gpu_pid_map'](call,Path(tmp))
        self.assertEqual(out['processes'],[{'gpu':1,'pid':123,'vram_mib':22000,'comm':'python'}])
        self.assertFalse(out['gpu1_owner_lease_verified'])

    def test_unknown_gpu_uuid_not_attributed_to_gpu1(self):
        a='GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        b='GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        def call(args):
            return (0,'0, '+a+'\n1, '+b+'\n') if '--query-gpu=index,uuid' in args else (0,'GPU-otherotherotherother, 123, 22000\n')
        self.assertEqual(context['gpu_pid_map'](call,Path('/none'))['status'],'HOLD_GPU_APP_BINDING')

    def test_oom_counter_requires_two_valid_monotonic_native_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'memory.events';f.write_text('oom 1\noom_kill 2\n')
            def increment(_):f.write_text('oom 3\noom_kill 2\n')
            out=context['cgroup_oom_pair'](f,increment)
            self.assertTrue(out['verified']);self.assertEqual(out['oom_delta'],2)
            self.assertFalse(context['cgroup_oom_pair'](f,lambda _:f.write_text('oom 0\noom_kill 0\n'))['verified'])
            f.write_text('high 8\n')
            self.assertFalse(context['cgroup_oom_pair'](f,lambda _:None)['verified'])

    def test_exact_embedded_shell_compiles_and_has_no_owner_claim(self):
        compile(code,'<v51-remote>','exec')
        self.assertIn('HOLD_NOT_PROVEN_BY_PID_INVENTORY',REMOTE)
        self.assertIn('NATIVE_P0_CGROUP_OOM=',REMOTE)
        self.assertIn('NATIVE_READ_ONLY_COMPLETE=true',REMOTE)

if __name__=='__main__':unittest.main()
