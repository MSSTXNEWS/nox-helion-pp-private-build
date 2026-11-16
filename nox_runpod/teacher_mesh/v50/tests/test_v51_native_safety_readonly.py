"""V51 source-only regression of the ACTUAL embedded native read-only functions."""
import ast
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import io
from contextlib import redirect_stdout
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as probe
from nox_runpod.teacher_mesh.v51.ephemeral_ssh_probe import REMOTE

code=REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
tree=ast.parse(code)
nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in {'gpu_pid_map','cgroup_oom_pair','supervisor_projection','bounded_native_json','pinned_owner_stop_snapshot','chat_listener_projection'}]
assert len(nodes)==6
context={'re':re,'json':json}
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

    def test_gpu_pid_log_budget_is_complete_json_or_explicit_hold(self):
        evidence={'status':'PID_ONLY_NO_OWNER_LEASE',
                  'gpu1_owner_lease_verified':False,
                  'processes':[{'gpu':1,'pid':123+i,'vram_mib':20000,
                                'comm':'python3_long_worker_process'} for i in range(12)]}
        original=json.dumps(evidence,sort_keys=True,separators=(',',':'))
        self.assertGreater(len(original),740)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(original[:740])
        bounded=context['bounded_native_json'](evidence,740,'HOLD_GPU_PID_LOG_BUDGET')
        self.assertLessEqual(len(bounded),740)
        self.assertEqual(json.loads(bounded),{'status':'HOLD_GPU_PID_LOG_BUDGET'})
        small={'status':'PID_ONLY_NO_OWNER_LEASE','processes':[]}
        self.assertEqual(json.loads(context['bounded_native_json'](
            small,740,'HOLD_GPU_PID_LOG_BUDGET')),small)
        self.assertEqual(json.loads(context['bounded_native_json'](
            {'verified':True,'oom_delta':0,'oom_kill_delta':0},
            260,'HOLD_CGROUP_OOM_LOG_BUDGET'))['verified'],True)

    def test_gpu_and_oom_evidence_never_use_unparseable_prefix_slices(self):
        self.assertIn('bounded_native_json(\n    gpu_pid_map',code)
        self.assertIn('HOLD_GPU_PID_LOG_BUDGET',code)
        self.assertNotIn("separators=(',',':'))[:740]",code)

    def test_supervisor_uses_existing_owner_only_p0_forwarding(self):
        workflow=(Path(__file__).resolve().parents[4]/'.github/workflows/nox-v51-ephemeral-ssh-native.yml').read_text()
        self.assertIn('"NATIVE_P0_"',workflow)
        self.assertIn("inputs.allow_native == 'YES'",workflow)
        self.assertIn('NATIVE_P0_SUPERVISOR_STATUS=',REMOTE)


    def test_pinned_stop_absence_is_not_global_manual_stop_clear(self):
        paths=tuple(str(i) for i in range(8))
        def missing(_):
            raise FileNotFoundError
        record=context['pinned_owner_stop_snapshot'](paths,missing)
        self.assertEqual(record['status'],'NO_STOP_IN_EIGHT_PINNED_PATHS')
        self.assertEqual(record['checked_count'],8)
        self.assertFalse(record['manual_stop_clear_verified'])

    def test_pinned_stop_detects_present_and_dangling_symlink_by_lstat(self):
        paths=tuple(str(i) for i in range(8))
        def exists(path):
            if path in ('2','7'): return object()
            raise FileNotFoundError
        record=context['pinned_owner_stop_snapshot'](paths,exists)
        self.assertEqual(record['status'],'STOP_PRESENT')
        self.assertEqual(record['present_ids'],[2,7])
        self.assertFalse(record['manual_stop_clear_verified'])

    def test_stop_read_is_fail_closed_on_scope_permission_and_race(self):
        paths=tuple(str(i) for i in range(8))
        def missing(_): raise FileNotFoundError
        self.assertEqual(context['pinned_owner_stop_snapshot'](paths[:7],missing)['status'],
                         'HOLD_STOP_SCOPE')
        def denied(path):
            if path=='3': raise PermissionError
            raise FileNotFoundError
        self.assertEqual(context['pinned_owner_stop_snapshot'](paths,denied)['status'],
                         'HOLD_STOP_IO')
        counter={'n':0}
        def changing(path):
            counter['n']+=1
            if path=='4' and counter['n']<=8: return object()
            raise FileNotFoundError
        self.assertEqual(context['pinned_owner_stop_snapshot'](paths,changing)['status'],
                         'HOLD_STOP_CHANGED_DURING_READ')

    def test_remote_pinned_paths_and_owner_only_forwarding(self):
        self.assertIn("'/root/nox/state/STOP.flag'",REMOTE)
        self.assertIn("'/workspace/NOX_STOP'",REMOTE)
        self.assertIn('NATIVE_P0_OWNER_STOP=',REMOTE)
        self.assertIn("pinned_owner_stop_snapshot(pinned_stop_paths, os.lstat)",REMOTE)
        self.assertIn("'manual_stop_clear_verified': False",code)


    def test_chat_listener_split_brain_blocks_blind_restart(self):
        status={'services':[{'service':'nox-chat-8081','status':'STOPPED','pid':None}]}
        line='LISTEN 0 128 127.0.0.1:8081 0.0.0.0:* users:(("llama-server",pid=7637,fd=12))\n'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'7637';p.mkdir()
            (p/'stat').write_text('7637 (llama-server) S '+' '.join(['0']*18+['123456']+['0']*10))
            (p/'comm').write_text('llama-server\n')
            x=context['chat_listener_projection'](status,lambda _: (0,line),Path(d))
        self.assertEqual(x['status'],'CHAT_UNMANAGED_LISTENER_OBSERVED')
        self.assertEqual(x['listener_pids'][0]['start_ticks'],123456)
        self.assertFalse(x['restart_authorized'])
        self.assertNotIn('users:',json.dumps(x))

    def test_chat_listener_fails_closed_on_unknown_pid_and_supervisor(self):
        parse=context['chat_listener_projection']
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            self.assertEqual(parse({},lambda _: (0,''),path)['status'],
                             'HOLD_CHAT_SUPERVISOR_NOT_OBSERVED')
            status={'services':[{'service':'nox-chat-8081','status':'STOPPED','pid':None}]}
            self.assertEqual(parse(status,lambda _: (99,''),path)['status'],
                             'HOLD_CHAT_LISTENER_QUERY')
            self.assertEqual(parse(status,lambda _: (0,'LISTEN 0 128 127.0.0.1:8081 0.0.0.0:*'),path)['status'],
                             'HOLD_CHAT_LISTENER_PID_UNREADABLE')

    def test_chat_listener_native_probe_is_readonly_and_forwarded(self):
        workflow=(Path(__file__).resolve().parents[4]/'.github/workflows/nox-v51-ephemeral-ssh-native.yml').read_text()
        self.assertIn('NATIVE_P0_CHAT_LISTENER=',REMOTE)
        self.assertIn('chat_listener_projection(supervisor_projection(rc,out),call,Path',REMOTE)
        self.assertIn('"NATIVE_P0_"',workflow)
        self.assertNotIn('supervisorctl restart',REMOTE)


    def test_readonly_metadata_429_then_success_respects_retry_after(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'{"instances":[]}'
        error=urllib.error.HTTPError(
            probe.LIST_API,429,"rate limited",{"Retry-After":"3"},None)
        with patch.object(probe.urllib.request,"urlopen",side_effect=[error,response]) as urlopen, \
             patch.object(probe.time,"sleep") as sleep:
            result=probe.api("GET","/instances/","test-key")
        self.assertEqual(result,{"instances":[]})
        self.assertEqual(urlopen.call_count,2)
        sleep.assert_called_once_with(3.0)

    def test_readonly_metadata_429_exhausts_after_two_retries(self):
        errors=[urllib.error.HTTPError(
            probe.LIST_API,429,"rate limited",{},None) for _ in range(3)]
        with patch.object(probe.urllib.request,"urlopen",side_effect=errors) as urlopen, \
             patch.object(probe.time,"sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"HOLD_VAST_API_HTTP_429"):
                probe.api("GET","/instances/","test-key")
        self.assertEqual(urlopen.call_count,3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[1.0,2.0])

    def test_mutating_429_and_transient_5xx_are_not_retried(self):
        mutation=urllib.error.HTTPError(
            probe.API+"/instances/60509551/ssh/",429,"rate limited",{},None)
        with patch.object(probe.urllib.request,"urlopen",side_effect=mutation) as urlopen, \
             patch.object(probe.time,"sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"HOLD_VAST_API_HTTP_429"):
                probe.api("POST","/instances/60509551/ssh/","test-key",{"public_key":"ssh-ed25519 test"})
        self.assertEqual(urlopen.call_count,1)
        sleep.assert_not_called()
        server_error=urllib.error.HTTPError(
            probe.LIST_API,503,"unavailable",{},None)
        with patch.object(probe.urllib.request,"urlopen",side_effect=server_error) as urlopen, \
             patch.object(probe.time,"sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"HOLD_VAST_API_HTTP_503"):
                probe.api("GET","/instances/","test-key")
        self.assertEqual(urlopen.call_count,1)
        sleep.assert_not_called()

    def test_429_retry_after_over_cap_fails_closed_without_retry(self):
        error=urllib.error.HTTPError(
            probe.LIST_API,429,"rate limited",{"Retry-After":"31"},None)
        with patch.object(probe.urllib.request,"urlopen",side_effect=error) as urlopen, \
             patch.object(probe.time,"sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"RETRY_AFTER_TOO_LONG"):
                probe.api("GET","/instances/","test-key")
        self.assertEqual(urlopen.call_count,1)
        sleep.assert_not_called()


    def test_attach_post_429_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            record=Path(tmp)/"cleanup.json"
            record.write_text(json.dumps({"public":"ssh-ed25519 AAAA KEY","key_id":None}))
            output=io.StringIO()
            with patch.object(probe,"TRACK",record), \
                 patch.object(probe,"api",side_effect=RuntimeError("HOLD_VAST_API_HTTP_429")) as post, \
                 patch.object(probe,"reconcile_attach_after_429",return_value=73) as reconcile, \
                 redirect_stdout(output):
                self.assertEqual(probe.attach_ephemeral_key("API-TOKEN-SECRET","ssh-ed25519 AAAA KEY"),[73])
            self.assertEqual(post.call_count,1)
            post.assert_called_once_with("POST","/instances/60509551/ssh/","API-TOKEN-SECRET",
                                        {"ssh_key":"ssh-ed25519 AAAA KEY"})
            reconcile.assert_called_once_with("API-TOKEN-SECRET","ssh-ed25519 AAAA KEY")
            self.assertNotIn("API-TOKEN-SECRET",output.getvalue())
            self.assertNotIn("ssh-ed25519 AAAA KEY",output.getvalue())
            self.assertEqual(json.loads(record.read_text())["attach_state"],"ATTACHED_VERIFIED")

    def test_cleanup_keeps_receipt_when_ambiguous_attach_is_not_visible_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            record=Path(tmp)/"cleanup.json"
            record.write_text(json.dumps({
                "public":"ssh-ed25519 AAAA PUBLIC", "key_id":None,
                "attach_state":"ATTACH_AMBIGUOUS_HTTP_429"}))
            output=io.StringIO()
            with patch.object(probe,"TRACK",record), \
                 patch.dict(probe.os.environ,{"NOX2":"TOKEN-SECRET"}), \
                 patch.object(probe,"match",return_value=[]), \
                 redirect_stdout(output):
                self.assertFalse(probe.cleanup())
            self.assertTrue(record.exists())
            self.assertIn("TEMP_SSH_CLEANUP=HOLD_ATTACH_STATE_UNRESOLVED",output.getvalue())
            self.assertNotIn("TOKEN-SECRET",output.getvalue())
            self.assertNotIn("ssh-ed25519",output.getvalue())

    def test_attach_429_reconciles_exact_public_key_once(self):
        with patch.object(probe,"match",return_value=[73]) as lookup:
            key_id=probe.reconcile_attach_after_429("NOX2-SECRET","ssh-ed25519 AAAA GENERATED")
        self.assertEqual(key_id,73)
        lookup.assert_called_once_with("NOX2-SECRET","ssh-ed25519 AAAA GENERATED")

    def test_attach_429_unmatched_key_holds_without_post_retry_or_key_output(self):
        secret="ssh-ed25519 AAAA GENERATED-SECRET"
        with patch.object(probe,"match",return_value=[]) as lookup:
            with self.assertRaisesRegex(RuntimeError,"RECONCILE_ABSENT") as caught:
                probe.reconcile_attach_after_429("API-TOKEN-SECRET",secret)
        lookup.assert_called_once_with("API-TOKEN-SECRET",secret)
        self.assertNotIn(secret,str(caught.exception))
        self.assertNotIn("API-TOKEN-SECRET",str(caught.exception))

    def test_attach_429_missing_list_endpoint_holds_with_safe_method_path_status(self):
        with patch.object(probe,"match",side_effect=RuntimeError("HOLD_VAST_API_HTTP_404")) as lookup:
            with self.assertRaisesRegex(RuntimeError,"GET_INSTANCE_SSH_HTTP_404") as caught:
                probe.reconcile_attach_after_429("API-TOKEN-SECRET","ssh-ed25519 AAAA SECRET")
        lookup.assert_called_once()
        self.assertNotIn("SECRET",str(caught.exception))
        self.assertNotIn("API-TOKEN-SECRET",str(caught.exception))

    def test_attach_reconcile_sanitizes_unexpected_exception_text(self):
        with patch.object(probe,"match",side_effect=RuntimeError("secret key and token leaked")) as lookup:
            with self.assertRaisesRegex(RuntimeError,"GET_INSTANCE_SSH_RECONCILE_FAILED") as caught:
                probe.reconcile_attach_after_429("TOKEN-SECRET","ssh-ed25519 AAAA KEY-SECRET")
        lookup.assert_called_once()
        self.assertNotIn("secret",str(caught.exception).lower())
        self.assertNotIn("TOKEN-SECRET",str(caught.exception))
        self.assertNotIn("KEY-SECRET",str(caught.exception))

if __name__=='__main__':unittest.main()
