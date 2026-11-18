"""Pure three-file composition for the accepted current four-queue install.

Read the actual private config in the existing maintenance transaction and
pass its exact bytes here. This module has no file/process/network side effects.
It neither fabricates missing config bytes nor substitutes an older catalog.
"""
from copy import deepcopy
import hashlib
import json
import re


BEFORE = {
    'scripts/owner_subagent_dispatcher.py':
        '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e',
    'scripts/owner_subagent_instruction_truth.py':
        'd03691b84954402558f1e23e1403043eb9c7d115eb57be575524c05502d0529a',
    'config/owner_native_subagents.json':
        'f283db153b763b8bc8e77dd57fedc3cd091c3a5336f40a6d9c805efbdf95d900',
}
AFTER_DISPATCHER = '5f134b8b1915851de15318e23885951885ca84d6515ca1e48c56286862830db5'
UNCHANGED = {
    'scripts/owner_autonomy_pool.py':
        '2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102',
    'scripts/owner_subagent_processes.py':
        'c1d5adfcc83300d749b42f66d50f41d5c62c4df52215e43cfc0b891e7c91101b',
    'scripts/owner_resource_policy.py':
        '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834',
}
NEXT_TASK_ID = '1V14-01.native4q.recovery_health.20261118'
DISPATCHER = 'scripts/owner_subagent_dispatcher.py'
TRUTH = 'scripts/owner_subagent_instruction_truth.py'
CONFIG = 'config/owner_native_subagents.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError('HOLD_CURRENT_RECOVERY_' + reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def prepare_change_set(preimages, dispatcher_source, *, request_id, source_commit):
    """Return postimage bytes, never a native-ready/installed assertion.

    Caller owns the existing exclusive maintenance lease, fresh physical CAS,
    queue/lifetime checks, private backup, inode-owned rollback and readback.
    The new TaskID must be absent in the final stopped authoritative queue.
    """
    require(isinstance(request_id, str) and re.fullmatch(r'[0-9]{1,24}', request_id), 'REQUEST')
    require(isinstance(source_commit, str) and re.fullmatch(r'[a-f0-9]{40}', source_commit), 'SOURCE')
    require(isinstance(preimages, dict) and set(preimages) == set(BEFORE), 'FILESET')
    for name, expected in BEFORE.items():
        raw = preimages[name]
        require(isinstance(raw, bytes) and len(raw) <= 262144 and sha(raw) == expected,
                'PREIMAGE_' + name.rsplit('/', 1)[-1])
    require(isinstance(dispatcher_source, bytes) and len(dispatcher_source) == 72630
            and sha(dispatcher_source) == AFTER_DISPATCHER, 'DISPATCHER_POSTIMAGE')
    compile(dispatcher_source, DISPATCHER, 'exec')
    old_pin = ("CALLBACK_SHA = '" + BEFORE[DISPATCHER] + "'").encode()
    require(preimages[TRUTH].count(old_pin) == 1, 'TRUTH_BINDING')
    truth = preimages[TRUTH].replace(old_pin,
        ("CALLBACK_SHA = '" + AFTER_DISPATCHER + "'").encode(), 1)
    compile(truth, TRUTH, 'exec')

    config = json.loads(preimages[CONFIG])
    require(isinstance(config, dict) and config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
        and type(config.get('instance_id')) is int and config['instance_id'] == 60509551
        and config.get('owner_authorized') is True and config.get('mode') == 'NORMAL'
        and type(config.get('target')) is int and config['target'] == 3
        and config.get('execution_mode') == 'NATIVE_LEAF_V1', 'CONFIG_SCOPE')
    catalog = config.get('catalog')
    require(isinstance(catalog, dict) and catalog.get('schema') == 'NOX_AUTONOMY_PROCESS_POOL_V1'
        and sha(encoded(catalog)) == config.get('catalog_sha256'), 'CATALOG_HASH')
    rows = catalog.get('tasks')
    require(isinstance(rows, list) and len(rows) == 7 and all(isinstance(row, dict) for row in rows)
        and len({row.get('id') for row in rows}) == 7
        and NEXT_TASK_ID not in {row['id'] for row in rows}, 'SEVEN_CURRENT_ROWS')
    old_rows = deepcopy(rows)
    reviews = [row for row in rows if row.get('handler') == 'owner_native_subagent_review']
    leaves = [row for row in rows if row.get('handler') == 'owner_native_typed_leaf']
    require(len(reviews) == 3 and len(leaves) == 4 and
        {row.get('params', {}).get('role') for row in reviews} == {'runtime','memory','weights'}, 'ROW_SCOPE')
    require({row.get('queue_id') for row in leaves} == {'Q1_RUNTIME_CHAT','Q2_MEMORY_KNOWLEDGE',
        'Q3_TRAINING_WEIGHTS','Q4_INTEGRATION_ACCEPTANCE'}, 'FOUR_QUEUES')
    for row in leaves:
        require(row.get('source_sha256') == BEFORE[DISPATCHER] and row.get('resource') == 'CPU_LIGHT', 'LEAF_SOURCE')
        row['source_sha256'] = AFTER_DISPATCHER
    health = [row for row in leaves if row.get('params') == {
        'operation':'chat_health', 'parent_task_id':'1V14-01'}]
    require(len(health) == 1 and health[0]['queue_id'] == 'Q1_RUNTIME_CHAT', 'HEALTH_LEAF_SCOPE')
    postinstall = deepcopy(health[0])
    postinstall.update(id=NEXT_TASK_ID, deps=[], priority='P0',
        title='Проверка здоровья чата после обновления восстановления исполнителей')
    rows.append(postinstall)
    # The first seven IDs/fields remain exact except the required leaf source pin.
    restored = deepcopy(rows[:7])
    for row in restored:
        if row['handler'] == 'owner_native_typed_leaf':
            row['source_sha256'] = BEFORE[DISPATCHER]
    require(restored == old_rows, 'HISTORY_CHANGED')
    pins = config.get('module_pins')
    require(isinstance(pins, dict), 'MODULE_PINS')
    for name in ('owner_autonomy_pool.py','owner_subagent_processes.py','owner_subagent_dispatcher.py'):
        expected = BEFORE[DISPATCHER] if name == 'owner_subagent_dispatcher.py' else UNCHANGED['scripts/'+name]
        require(pins.get(name) == expected, 'MODULE_PIN_' + name)
    pins['owner_subagent_dispatcher.py'] = AFTER_DISPATCHER
    config.update(catalog_sha256=sha(encoded(catalog)), owner_request=request_id, owner_source_sha=source_commit)
    changes = {DISPATCHER:dispatcher_source, TRUTH:truth, CONFIG:encoded(config)}
    return changes, {
        'schema':'NOX_CURRENT_FOUR_QUEUE_RECOVERY_COMPOSITION_V1',
        'next_task_id':NEXT_TASK_ID, 'new_operation':'chat_health',
        'source_postimages':{name:{'sha256':sha(raw), 'bytes':len(raw)} for name,raw in changes.items()},
        'catalog_prior_rows':7, 'catalog_result_rows':8,
        'historical_queue_writes':0, 'original_tasks_accepted':0,
        'native_effects_performed':False,
    }
