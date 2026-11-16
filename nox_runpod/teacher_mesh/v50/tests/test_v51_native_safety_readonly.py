"""V51 source-only regression of the ACTUAL embedded native read-only functions."""
import ast
import re
import tempfile
import unittest
from pathlib import Path
from nox_runpod.teacher_mesh.v51.ephemeral_ssh_probe import REMOTE

code=REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
tree=ast.parse(code)
nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in {'gpu_pid_map','cgroup_oom_pair','supervisor_projection'}]
assert len(nodes)==3
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

    def test_supervisor_rc3_preserves_actual_fatal_and_running_pid_without_raw_reason(self):
        raw=('caddy RUNNING pid 179, uptime 2 days\n'
             'nox-dispatcher-t855u RUNNING pid 498177, uptime 1 hour\n'
             'nox-priority-scheduler RUNNING pid 498221, uptime 1 hour\n'
             'nox-selfheal RUNNING pid 498241, uptime 1 hour\n'
             'nox-train-volta-t866u FATAL Exited too quickly private=secret\n'
             'nox-chat-8081 STOPPED Nov 14\n')
        row=context['supervisor_projection'](3,raw)
        self.assertEqual(row['state'],'OBSERVED_PARTIAL')
        self.assertEqual(row['supervisor_rc'],3)
        self.assertFalse(row['all_running_verified'])
        self.assertEqual(len(row['services']),5)
        self.assertEqual(row['services'][0]['pid'],498177)
        self.assertEqual(row['services'][-2]['status'],'FATAL')
        self.assertNotIn('secret',str(row))
        self.assertNotIn('caddy',str(row))

    def test_supervisor_zero_and_partial_starting(self):
        parse=context['supervisor_projection']
        one='nox-selfheal RUNNING pid 498241, uptime 1 hour\n'
        self.assertEqual(parse(0,one)['state'],'OBSERVED_PARTIAL')
        self.assertFalse(parse(0,one)['all_running_verified'])
        all_five=''.join(f'{name} RUNNING pid {100+i}, uptime 1 hour\n'
                         for i,name in enumerate(('nox-dispatcher-t855u','nox-priority-scheduler',
                              'nox-selfheal','nox-train-volta-t866u','nox-chat-8081')))
        self.assertEqual(parse(0,all_five)['state'],'OBSERVED_ALL_RUNNING')
        self.assertTrue(parse(0,all_five)['all_running_verified'])
        self.assertFalse(parse(3,'nox-train-volta-t866u STARTING\n')['all_running_verified'])

    def test_supervisor_duplicate_no_false_full_health(self):
        parse=context['supervisor_projection']
        one='nox-selfheal RUNNING pid 999, uptime 1 hour\n'
        result=parse(0,one+one)
        self.assertEqual(result['state'],'HOLD_SUPERVISOR_DUPLICATE')
        self.assertEqual(result['services'],[])

    def test_supervisor_rejects_ambiguous_or_unbounded_rows(self):
        parse=context['supervisor_projection']
        self.assertEqual(parse(99,'nox-selfheal RUNNING pid 1,\n')['state'],'HOLD_SUPERVISOR_COMMAND')
        self.assertEqual(parse(3,'nox-selfheal OKAY pid 1,\n')['state'],'HOLD_SUPERVISOR_SCHEMA')
        self.assertEqual(parse(3,'nox-selfheal RUNNING uptime 12\n')['state'],'HOLD_SUPERVISOR_PID')
        self.assertEqual(parse(3,'caddy STOPPED\n')['state'],'HOLD_SUPERVISOR_NO_CORE')
        self.assertEqual(parse(3,'nox-selfheal RUNNING pid 1,\n'*41)['state'],'HOLD_SUPERVISOR_BOUNDS')
        self.assertEqual(parse(3,'')['state'],'HOLD_SUPERVISOR_BOUNDS')

    def test_supervisor_uses_existing_owner_only_p0_forwarding(self):
        workflow=(Path(__file__).resolve().parents[4]/'.github/workflows/nox-v51-ephemeral-ssh-native.yml').read_text()
        self.assertIn('"NATIVE_P0_"',workflow)
        self.assertIn("inputs.allow_native == 'YES'",workflow)
        self.assertIn('NATIVE_P0_SUPERVISOR_STATUS=',REMOTE)

if __name__=='__main__':unittest.main()
