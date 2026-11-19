import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('owner_training_status_binding',HERE/'owner_training_status_binding.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

PROXY_FIXTURE=('async def route(_owner,_utext):\n'
    '    _self_query=False\n    payload={}\n    body={}\n'
    '    if _owner:\n'
    '        from owner_chat_stream import owner_request_query as _nox_owner_request_query\n'
    '        _self_query = _self_query or _nox_owner_request_query(_utext)\n'
    '    payload["messages"] = await _nox_chat_asyncio.to_thread(\n'
    '        lambda: _trim_ctx(_build_messages(body)))\n'
    '    return payload\n').encode()


class BindingTests(unittest.TestCase):
    def test_training_status_intent_without_general_lora_tax(self):
        for text in ('Как идёт обучение?','Сколько обновлений optimizer сейчас у NOX?',
                     'Последние веса уже слиты?', 'Какой статус обучения Нокс?',
                     'Ты уже обучен?', 'Что сохранилось из checkpoint?',
                     'Обучение идёт сейчас?'):
            self.assertTrue(b.training_query(text),text)
        for text in ('17 * 19','Нарисуй круг','Что такое LoRA?',
                     'Объясни обучение моделей','Explain optimizer internals','',None,'a'*8001):
            self.assertFalse(b.training_query(text),text)

    def test_ordinary_turn_has_no_training_reader_call_and_no_copy(self):
        messages=[{'role':'user','content':'17 * 19'}]
        with patch.object(b,'current_training',side_effect=AssertionError('training I/O')):
            self.assertIs(b.augment_messages(messages,'17 * 19'),messages)

    def test_fact_injection_preserves_messages_and_explicit_unknowns(self):
        messages=[{'role':'system','content':'existing current inventory'},
                  {'role':'user','content':'NOX, сколько обновлений optimizer?'}]
        facts={'state':'RUNNING','global_step':None,'optimizer_steps':None,
               'positive_optimizer_steps_verified':False,'current_run':{'global_step':1}}
        with patch.object(b,'current_training',return_value=facts):
            value=b.augment_messages(messages,messages[-1]['content'])
        self.assertEqual(messages[0]['content'],'existing current inventory')
        self.assertEqual(value[1],messages[1]);self.assertIsNot(value,messages)
        self.assertIn('"optimizer_steps":null',value[0]['content'])
        self.assertIn('Телеметрия шага сама по себе',value[0]['content'])
        self.assertIn(b.MARKER,value[0]['content'])

    def test_exact_proxy_transition_compiles_is_idempotent_and_routes_owner_only(self):
        with patch.object(b,'PROXY_BEFORE',hashlib.sha256(PROXY_FIXTURE).hexdigest()):
            changed=b.patch_proxy(PROXY_FIXTURE)
            self.assertEqual(changed,b.patch_proxy(changed))
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN'):
                b.patch_proxy(changed+b'# foreign\n')
        ns={'_nox_chat_asyncio':asyncio,'_trim_ctx':lambda rows:rows,
            '_build_messages':lambda body:[{'role':'system','content':'existing'}]}
        exec(compile(changed,'<proxy-fixture>','exec'),ns)
        fake_stream=types.ModuleType('owner_chat_stream');fake_stream.owner_request_query=lambda _:False
        with patch.dict(sys.modules,{'owner_chat_stream':fake_stream,'owner_training_status_binding':b}):
            with patch.object(b,'current_training',side_effect=AssertionError('training I/O')):
                self.assertEqual(asyncio.run(ns['route'](True,'17 * 19'))['messages'][0]['content'],'existing')
                self.assertEqual(asyncio.run(ns['route'](False,'NOX сколько обновлений optimizer?'))['messages'][0]['content'],'existing')
            with patch.object(b,'current_training',return_value={'state':'RUNNING'}):
                observed=asyncio.run(ns['route'](True,'NOX сколько обновлений optimizer?'))
                self.assertIn('"state":"RUNNING"',observed['messages'][0]['content'])

    def test_real_v137_exact_preimage_keeps_current_inventory_binding(self):
        raw=(HERE.parent/'nox_runpod/teacher_mesh/v137/owner_self_observation.py').read_text()
        raw=raw.replace('        if rc != 0:\n            raise RuntimeError("HOLD_SUPERVISOR_READ")',
                        '        if rc not in (0,3):\n            raise RuntimeError("HOLD_SUPERVISOR_READ")',1).encode()
        raw+=(b'\n# NOX_OWNER_CURRENT_DOWNLOAD_EVIDENCE_V1\n'
              b'from owner_chat_evidence import bind_self_observation as _nox_bind_current_evidence\n'
              b'_nox_bind_current_evidence(globals())\n')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),b.OBSERVER_BEFORE)
        changed=b.patch_self_observation(raw)
        self.assertTrue(changed.startswith(raw));self.assertEqual(changed,b.patch_self_observation(changed))
        with self.assertRaisesRegex(ValueError,'SOURCE_PIN'):
            b.patch_self_observation(changed+b'# changed\n')


if __name__=='__main__':unittest.main()
