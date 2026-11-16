"""Local synthetic fixtures only: no native, HTTP, service, credential or model I/O."""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('owner_post_reset_state_observe.py')
spec = importlib.util.spec_from_file_location('post_reset_fixture', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deadline = time.monotonic() + 20

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    def record(self, raw):
        path = self.write(self.root / 'record', raw)
        return m.read_record(path, 262144, self.deadline)

    def test_flags_only_export_metadata_and_exact_known_request(self):
        row = self.record(b'OWNER_MODEL_UPDATE 6917926683\n')
        projected = m.flag_projection('OWNER_STOP', row)
        self.assertEqual(projected['owner_request'], '6917926683')
        self.assertEqual(projected['sha256'], hashlib.sha256(row['raw']).hexdigest())
        self.assertNotIn('raw', projected)
        secret = b'private history and password=SECRET_TEST_ONLY\n'
        unknown = m.flag_projection('OWNER_STOP', self.record(secret))
        self.assertIsNone(unknown['owner_request'])
        self.assertEqual(unknown['known_format'], 'UNKNOWN_CONTENT_WITHHELD')
        self.assertNotIn('SECRET_TEST_ONLY', json.dumps(unknown))
        extra = m.flag_projection('OWNER_STOP', self.record(b'OWNER_MODEL_UPDATE 6917926683\nextra'))
        self.assertIsNone(extra['owner_request'])

    def test_symlink_parent_leaf_and_bounds_are_rejected_before_content(self):
        target = self.write(self.root / 'real' / 'payload', b'private')
        parent = self.root / 'alias'; parent.symlink_to(target.parent, target_is_directory=True)
        leaf = self.root / 'leaf'; leaf.symlink_to(target)
        with patch.object(m.os, 'read', wraps=os.read) as read:
            for path in (parent / 'payload', leaf):
                with self.assertRaises(OSError):
                    m.read_record(path, 100, self.deadline)
            self.assertEqual(read.call_count, 0)
        with self.assertRaisesRegex(m.ObservationHold, 'REGULAR_FILE_BOUND'):
            m.read_record(target, 2, self.deadline)

    def test_same_bytes_foreign_inode_race_is_detected_without_overwrite(self):
        path = self.write(self.root / 'owned', b'exact')
        real_read = os.read
        replaced = False
        def read(fd, count):
            nonlocal replaced
            value = real_read(fd, count)
            if not replaced:
                replaced = True
                foreign = self.write(self.root / 'replacement', b'exact')
                os.replace(foreign, path)
            return value
        with patch.object(m.os, 'read', side_effect=read), self.assertRaisesRegex(m.ObservationHold, 'FILE_CHANGED'):
            m.read_record(path, 100, self.deadline)
        self.assertEqual(path.read_bytes(), b'exact')

    def test_deadline_closes_owned_fds_and_is_not_swallowed(self):
        path = self.write(self.root / 'file', b'bounded')
        real_open, real_close = os.open, os.close
        opened = set()
        def op(*args, **kwargs):
            fd = real_open(*args, **kwargs); opened.add(fd); return fd
        def close(fd):
            opened.discard(fd); return real_close(fd)
        with patch.object(m.os, 'open', side_effect=op), patch.object(m.os, 'close', side_effect=close),\
             patch.object(m.os, 'read', side_effect=m.Deadline), self.assertRaises(m.Deadline):
            m.read_record(path, 100, self.deadline)
        self.assertEqual(opened, set())

    def test_json_and_journal_binding_withhold_arbitrary_fields(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]'):
            with self.assertRaises(m.ObservationHold): m.document(raw)
        request = '6918022617'
        value = {'schema':'NOX_OWNER_EMERGENCY_RESET_V1', 'request':request,
            'source_sha':m.JOURNALS[request], 'state':'MODEL_UPDATE_STOP_DONE_EXACT_OLD_GGUF_CLEANUP',
            'stop_verified':True, 'maintenance_flags_active':True,
            'supervisor_after':{'nox-proxy':'STOPPED','nox-train-volta-t866u':'FATAL'},
            's03_backup':{'bytes':49037312,'sha256':'a'*64,'raw':'PRIVATE_DB'},
            'deleted':[{'path':'PRIVATE_PATH','contents':'PRIVATE_HISTORY'}], 'secret':'SECRET_TEST_ONLY'}
        row = self.record(json.dumps(value).encode())
        result = m.journal_projection(request, row)
        text = json.dumps(result)
        for hidden in ('PRIVATE_DB','PRIVATE_PATH','PRIVATE_HISTORY','SECRET_TEST_ONLY'): self.assertNotIn(hidden,text)
        self.assertEqual(result['s03_backup'], {'bytes':49037312,'sha256':'a'*64})
        self.assertEqual(result['service_state_scope'],'HISTORICAL_RESET_JOURNAL_NOT_CURRENT_SERVICE_PROOF')
        value['source_sha'] = '0'*40
        with self.assertRaisesRegex(m.ObservationHold,'JOURNAL_BINDING'):
            m.journal_projection(request, self.record(json.dumps(value).encode()))

    def checkpoint(self, output):
        name = 'checkpoint-u00000055-a00000055-g01794833901774705882'
        state = {'successful_total':55,'attempted_total':55,'skipped_total':0,
                 'holdout_evaluated_successful_total':55,'last_holdout_loss':1.3,
                 'private_history':'SECRET_TEST_ONLY'}
        raw = json.dumps(state).encode()
        files = {n:'a'*64 for n in m.PAYLOADS}; files['student_state.json'] = m.digest(raw)
        manifest = {'directory':name,'successful_total':55,'attempted_total':55,'files_sha256':files}
        manifest_raw = json.dumps(manifest).encode()
        self.write(output/name/'student_state.json',raw)
        self.write(output/name/'checkpoint_manifest.json',manifest_raw)
        self.write(output/'latest_checkpoint.json',json.dumps({'directory':name,'manifest_sha256':m.digest(manifest_raw)}).encode())
        return name

    def test_checkpoint_reads_only_three_jsons_and_rejects_path_escape(self):
        output = self.root/'output'; self.checkpoint(output)
        opened = []
        def read(label,path,maximum):
            opened.append(path.name); return m.read_record(path,maximum,self.deadline)
        with patch.object(m,'OUTPUT',output):
            result = m.checkpoint_projection(read)
            self.assertEqual(opened,['latest_checkpoint.json','checkpoint_manifest.json','student_state.json'])
            self.assertEqual(result['counters']['successful_total'],55)
            self.assertFalse(result['full_payload_sha256_verified'])
            self.assertNotIn('SECRET_TEST_ONLY',json.dumps(result))
            self.write(output/'latest_checkpoint.json',b'{"directory":"../../outside","manifest_sha256":"'+b'a'*64+b'"}')
            opened.clear()
            with self.assertRaisesRegex(m.ObservationHold,'CHECKPOINT_PATH_SCOPE'): m.checkpoint_projection(read)
            self.assertEqual(opened,['latest_checkpoint.json'])

    def test_guard_reports_staleness_and_real_field_names_without_permission(self):
        value = {'state':'INHIBITED','sampled_at':time.time()-120,
                 'policy_state':{'inhibit':True,'reason':'HOLDOUT_REGRESSION','latched_at':1,
                    'last_successful_updates':55,'last_evaluation_update':55,'regression_streak':2},
                 'checkpoint':{'successful_updates':55,'manifest_sha256':'a'*64,'private':'SECRET_TEST_ONLY'},
                 'bindings':{'private':'SECRET_TEST_ONLY'}}
        result = m.guard_projection(self.record(json.dumps(value).encode()))
        self.assertEqual(result['policy']['last_evaluation_update'],55)
        self.assertFalse(result['fresh_within_30_seconds'])
        self.assertFalse(result['permission_to_resume'])
        self.assertNotIn('SECRET_TEST_ONLY',json.dumps(result))

    def test_health_is_only_get_without_body_or_redirect(self):
        calls = []
        class Connection:
            def __init__(self,host,port,timeout): calls.append(('connect',host,port,timeout))
            def request(self,*args): calls.append(('request',*args))
            def getresponse(self): return types.SimpleNamespace(status=302,read=lambda *_:self.fail())
            def close(self): calls.append(('close',))
        with patch.object(m.http.client,'HTTPConnection',Connection): result=m.health(8081,self.deadline)
        self.assertEqual(result['status'],302)
        self.assertEqual(result['response_body_bytes_read'],0)
        self.assertFalse(result['redirect_followed'])
        self.assertEqual([c for c in calls if c[0]=='request'],[('request','GET','/health')])
        self.assertLessEqual(calls[0][3],1.0)

    def test_supervisor_command_is_status_only_and_hides_unparsed_output(self):
        response=types.SimpleNamespace(returncode=3,stdout=b'nox-proxy RUNNING pid 42, uptime SECRET_TEST_ONLY\nnox-train-volta-t866u FATAL private error\nplatform RUNNING pid 7\n')
        with patch.object(m.subprocess,'run',return_value=response) as run: result=m.services(self.deadline)
        self.assertEqual(run.call_args.args[0],['supervisorctl','status'])
        self.assertEqual(result['services']['nox-proxy'],{'state':'RUNNING','pid':42})
        self.assertNotIn('platform',result['services'])
        self.assertNotIn('SECRET_TEST_ONLY',json.dumps(result))

    def test_cgroup_zero_stat_size_accepts_bounded_live_value_and_rejects_oversize(self):
        info = types.SimpleNamespace(st_dev=1,st_ino=2,st_mode=0o100644,st_uid=0,st_gid=0,
             st_nlink=1,st_size=0,st_mtime_ns=0,st_ctime_ns=0)
        with patch.object(m,'open_regular',side_effect=[(10,info),(11,info)]),\
             patch.object(m.os,'fstat',return_value=info),patch.object(m.os,'read',side_effect=[b'123\n',b'']),\
             patch.object(m.os,'close') as close:
            row=m.resource_value(self.root/'memory.current',self.deadline)
        self.assertEqual(row['value_bytes'],123)
        self.assertFalse(row['unlimited'])
        self.assertEqual({call.args[0] for call in close.call_args_list},{10,11})
        with patch.object(m,'open_regular',return_value=(10,info)),\
             patch.object(m.os,'read',return_value=b'1'*129),patch.object(m.os,'close'),\
             self.assertRaisesRegex(m.ObservationHold,'RESOURCE_BOUND'):
            m.resource_value(self.root/'memory.current',self.deadline)

    def test_resources_unknown_and_unlimited_are_not_zero_or_admission(self):
        group=self.root/'cgroup'
        self.write(group/'memory.current',b'100\n');self.write(group/'memory.max',b'1000\n')
        self.write(group/'memory.swap.max',b'max\n')
        with patch.object(m,'CGROUP',group),patch.object(m,'FILESYSTEMS',{'SSD':self.root}):
            row=m.resources(self.deadline)
            self.assertEqual(row['memory_headroom_bytes'],900)
            self.assertEqual(row['cgroup']['memory.swap.current']['state'],'UNKNOWN')
            self.assertTrue(row['cgroup']['memory.swap.max']['unlimited'])
            self.assertIsNone(row['cgroup']['memory.swap.max']['value_bytes'])
            self.assertGreater(row['filesystems']['SSD']['free_bytes'],0)
            self.write(group/'memory.current',b'110\n')
            later=m.resources(self.deadline)
            self.assertEqual(later['memory_headroom_bytes'],890)
            self.write(group/'memory.max',b'max\n')
            self.assertIsNone(m.resources(self.deadline)['memory_headroom_bytes'])
        self.assertEqual(row['scope'],'SAMPLED_TELEMETRY_NOT_ADMISSION_OR_RESUME_PERMISSION')

    def test_final_read_detects_flag_change_and_preserves_partial_evidence(self):
        output=self.root/'output';self.checkpoint(output)
        stop=self.write(self.root/'STOP',b'OWNER_MODEL_UPDATE 6917926683\n')
        state=self.root/'state';state.mkdir()
        def health(port,deadline):
            self.write(stop,b'OWNER_MODEL_UPDATE 6918022617\n')
            return {'port':port,'status':None,'error_type':'ConnectionRefusedError'}
        with patch.object(m,'ROOT',self.root),patch.object(m,'STATE',state),patch.object(m,'OUTPUT',output),\
             patch.object(m,'FLAGS',{'OWNER_STOP':stop}),patch.object(m,'JOURNALS',{}),\
             patch.object(m,'services',return_value={'state':'CURRENT_STATUS_OBSERVED'}),patch.object(m,'health',side_effect=health),\
             patch.object(m,'resources',return_value={'scope':'SYNTHETIC_ONLY'}):
            result=m.observe(self.deadline)
        self.assertEqual(result['flags']['OWNER_STOP']['owner_request'],'6917926683')
        self.assertEqual(result['changed_during_observation'],['OWNER_STOP'])
        self.assertFalse(result['observation_complete'])
        result={}
        with patch.object(m,'FLAGS',{'OWNER_STOP':stop}),patch.object(m,'JOURNALS',{}),\
             patch.object(m,'checkpoint_projection',side_effect=m.Deadline),self.assertRaises(m.Deadline):
            m.observe(self.deadline,result)
        self.assertIn('OWNER_STOP',result['flags'])
        self.assertFalse(result['observation_complete'])

    def test_ast_effect_scope_and_exact_fixed_roots(self):
        source=SOURCE.read_text();tree=ast.parse(source)
        forbidden={'O_WRONLY','O_RDWR','O_CREAT','O_TRUNC','O_APPEND','O_EXCL','unlink','rename','replace','chmod','chown','kill','killpg','mkdir','write_bytes','write_text'}
        attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
        self.assertFalse(attrs & forbidden)
        self.assertEqual(set(m.FLAGS),{'OWNER_STOP','OWNER_MAINTENANCE','TRAIN_HOLD','TRAIN_PAUSE'})
        self.assertEqual(set(m.JOURNALS),{'6917926683','6918022617'})
        self.assertEqual(m.SECONDS,20)
        self.assertNotIn('BUNDLE',source)
        imports={n.names[0].name.split('.')[0] for n in tree.body if isinstance(n,ast.Import)}
        self.assertFalse(imports & {'pickle','torch','requests','sqlite3'})
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='run']
        self.assertEqual(len(calls),1)
        self.assertEqual(ast.literal_eval(calls[0].args[0]),['supervisorctl','status'])


if __name__=='__main__': unittest.main()
