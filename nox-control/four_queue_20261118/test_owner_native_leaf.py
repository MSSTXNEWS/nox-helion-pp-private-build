"""Source QA, including real LOCAL CPU/IPC processes; not OneHost acceptance."""
import hashlib
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

import owner_subagent_dispatcher as binding
from owner_subagent_processes import GateError, Subagents


HERE = Path(__file__).parent


def pins():
    return {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            for name in binding.LEAF_SOURCE_FILES}


def leaf_item(number, role='runtime'):
    return {'id':'I-48.local-unit.'+str(number), 'subagent':role,
            'task':'Execute the pinned four-queue regression subset', 'depends_on':[],
            '_native_leaf_context':{'operation':'queue_regression', 'parent_task_id':'I-48',
                'queue_id':'Q4_INTEGRATION_ACCEPTANCE', 'claim':'a'*24,
                'source_sha256':hashlib.sha256((HERE/'owner_subagent_dispatcher.py').read_bytes()).hexdigest(),
                'source_pins':pins()}}


class NativeLeafTests(unittest.TestCase):
    def test_three_real_local_processes_execute_and_reuse_same_pid(self):
        roles = list(binding.ROLES)
        with Subagents(roles, timeout=20) as pool:
            initial = {role: process.pid for role, process in pool.processes.items()}
            self.assertEqual(len(set(initial.values())), 3)
            for n, role in enumerate(roles):
                pool.submit(leaf_item(n, role))
            events = []
            deadline = time.monotonic()+20
            while len(events) < 3 and time.monotonic() < deadline:
                event = pool.poll(timeout=.2)
                if event:
                    events.append(event)
            self.assertEqual(len(events), 3)
            for event in events:
                self.assertEqual(event['state'], 'NATIVE_LEAF_COMPLETED')
                self.assertTrue(event['leaf_evidence']['check_passed'])
                self.assertFalse(event['leaf_evidence']['original_task_accepted'])
                self.assertFalse(event['leaf_evidence']['model_called'])
                self.assertEqual(event['pid'], initial[event['role']])
            pool.submit(leaf_item(4, roles[0]))
            event = None
            while event is None and time.monotonic() < deadline:
                event = pool.poll(timeout=.2)
            self.assertIsNotNone(event)
            self.assertEqual(event['state'], 'NATIVE_LEAF_COMPLETED')
            self.assertEqual(event['pid'], initial[roles[0]])
            first = next(item for item in events if item['role'] == roles[0])
            self.assertEqual(event['leaf_evidence']['worker']['process_starttime'],
                             first['leaf_evidence']['worker']['process_starttime'])

    def test_bad_source_or_wrong_queue_never_executes(self):
        item = leaf_item(0)
        item['_native_leaf_context']['source_sha256'] = '0'*64
        with self.assertRaisesRegex(GateError, 'HOLD_NATIVE_LEAF_CONTEXT'):
            binding.execute_native_leaf(item)
        item = leaf_item(0)
        item['_native_leaf_context']['queue_id'] = 'Q1_RUNTIME_CHAT'
        with self.assertRaisesRegex(GateError, 'HOLD_NATIVE_LEAF_QUEUE'):
            binding.execute_native_leaf(item)

    def test_http_error_json_is_not_health_pass(self):
        item = leaf_item(0)
        item['_native_leaf_context'].update(operation='chat_health', parent_task_id='1V14-01',
                                            queue_id='Q1_RUNTIME_CHAT')
        with patch.object(binding, '_local_json', return_value=({'status':'error'}, 1.0)):
            result = binding.execute_native_leaf(item)
        self.assertFalse(result['leaf_evidence']['check_passed'])
        self.assertFalse(result['leaf_evidence']['original_task_accepted'])

    def test_leaf_working_set_does_not_call_model_slots(self):
        native = binding.Native.__new__(binding.Native)
        native.ns = {'_qlock':threading.RLock()}
        native.state = {'tasks':{'outside':{'handler':'other', 'status':'running'},
                                'leaf':{'handler':binding.LEAF_HANDLER, 'status':'pending',
                                        'queue_id':'Q3_TRAINING_WEIGHTS', 'native_queue_sequence':1}}}
        native.catalog = {'tasks':[{'id':'leaf', 'handler':binding.LEAF_HANDLER}]}
        native.stop_active = lambda:False
        native.owner_allowed = lambda:True
        mib = 1024*1024
        files = {'memory.current':str(1900*mib), 'memory.max':str(2048*mib),
                 'cpu.pressure':'some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n',
                 'memory.stat':'inactive_file '+str(700*mib)+'\nfile '+str(1000*mib)+'\nshmem '+str(100*mib)+'\n',
                 'memory.pressure':'some avg10=0.00 avg60=0 total=0\nfull avg10=0.00 avg60=0 total=0\n'}
        with patch.object(Path, 'read_text', lambda path,*args,**kwargs:files[path.name]), \
             patch.object(binding.urllib.request, 'build_opener') as opener:
            snapshot = native.read_resource_snapshot(leaf_only=True)
        opener.assert_not_called()
        self.assertEqual(snapshot['task_status'], {'leaf':'pending'})
        self.assertEqual(snapshot['queue_cursor'], 3)
        self.assertAlmostEqual(snapshot['cgroup_memory_ratio'], 1584/2048)
        self.assertAlmostEqual(snapshot['raw_cgroup_memory_ratio'], 1900/2048)
        self.assertIsNone(binding.resource_wait_reason(snapshot))

    def test_memory_pressure_still_holds_cpu_leaf(self):
        native = binding.Native.__new__(binding.Native)
        mib = 1024*1024
        files = {'memory.current':str(1900*mib), 'memory.max':str(2048*mib),
                 'cpu.pressure':'some avg10=0.00 avg60=0 total=0\n',
                 'memory.stat':'inactive_file 700\nfile 1000\nshmem 100\n',
                 'memory.pressure':'some avg10=1.00 avg60=0 total=0\nfull avg10=0.00 avg60=0 total=0\n'}
        with patch.object(Path, 'read_text', lambda path,*args,**kwargs:files[path.name]):
            with self.assertRaisesRegex(GateError, 'HOLD_NATIVE_LEAF_MEMORY_PRESSURE'):
                native.read_resource_snapshot(leaf_only=True)

    def test_parent_id_is_not_an_executable_leaf_id(self):
        native = binding.Native.__new__(binding.Native)
        native.config = {'execution_mode':binding.LEAF_MODE, 'leaf_source_pins':pins()}
        native.source = 'b'*64
        native.policy = {'sha256':'c'*64}
        task = {'id':'I-48', 'queue_id':'Q4_INTEGRATION_ACCEPTANCE',
                'handler':binding.LEAF_HANDLER, 'source_sha256':native.source,
                'params':{'operation':'queue_regression', 'parent_task_id':'I-48'}}
        with self.assertRaisesRegex(GateError, 'HOLD_NATIVE_LEAF_CATALOG_SCOPE'):
            native._validate_catalog({'schema':binding.autonomy.SCHEMA, 'tasks':[task]})

    def test_existing_catalog_and_four_leaf_children_bind_together(self):
        source = hashlib.sha256((HERE/'owner_subagent_dispatcher.py').read_bytes()).hexdigest()
        rows = [{'id':'legacy.'+role, 'handler':binding.HANDLER, 'source_sha256':'b'*64,
                 'params':{'role':role}} for role in binding.ROLES]
        parents = ('1V14-01', '3A02', '4A03', 'I-48')
        rows += [{'id':parent+'.native4q.unit', 'handler':binding.LEAF_HANDLER,
                  'queue_id':binding.LEAF_OPERATIONS[operation][0], 'source_sha256':source,
                  'params':{'operation':operation, 'parent_task_id':parent}}
                 for parent, operation in zip(parents, binding.LEAF_OPERATIONS)]
        catalog = {'schema':binding.autonomy.SCHEMA, 'tasks':rows}
        config = {'schema':binding.SCHEMA, 'policy_id':binding.POLICY_ID,
                  'mode':'NORMAL', 'target':3, 'execution_mode':binding.LEAF_MODE,
                  'policy':{'sha256':'b'*64}, 'catalog':catalog,
                  'catalog_sha256':binding.digest(binding.encoded(catalog)), 'leaf_source_pins':pins(),
                  'module_pins':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                     for name in ('owner_subagent_processes.py', 'owner_autonomy_pool.py', 'owner_subagent_dispatcher.py')}}
        with patch.object(binding, 'owner_config', return_value=config), \
             patch.object(binding, 'load_policy', return_value=('policy', {})):
            native = binding.Native({'_qlock':threading.RLock()})
            self.assertEqual(native.read_reviewed_catalog(), catalog)
        native.state = {'tasks':{'legacy.'+role:{'status':'done'} for role in binding.ROLES}}
        self.assertTrue(native._leaf_only_work())
        native.state['tasks']['legacy.runtime']['status'] = 'pending'
        self.assertFalse(native._leaf_only_work())


if __name__ == '__main__':
    unittest.main()
