import asyncio
import base64
import hashlib
import json
from pathlib import Path
import types
import unittest
from unittest.mock import AsyncMock, patch

import owner_chat_browser_release_qa as release
import owner_browser_release_qa_entry as entry


def installed():
    raw=Path('owner_chat_browser_qa.py').read_bytes()
    traw=Path('owner_chat_browser_transport_qa.py').read_bytes()
    core=types.ModuleType('qa_release_core_test');transport=types.ModuleType('qa_release_transport_test')
    exec(compile(raw,'<base>','exec'),core.__dict__)
    exec(compile(traw,'<transport>','exec'),transport.__dict__)
    original=core.progressive_stream_valid
    core=release.install(core,raw,transport,traw)
    return core,original


class ReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_missing_then_busy_then_ready_is_read_only(self):
        page=types.SimpleNamespace(evaluate=AsyncMock(side_effect=[
            {'count':0,'present':False,'disabled':None,'phase':'thinking'},
            {'count':1,'present':True,'disabled':True,'phase':'speaking'},
            {'count':1,'present':True,'disabled':False,'phase':'done'}]))
        report={}
        with patch.object(release.asyncio,'sleep',new=AsyncMock()):
            await release.wait_send_release(page,report,lambda:False)
        self.assertEqual(report['send_release_observation']['state'],'READY')
        self.assertEqual(page.evaluate.await_count,3)
        self.assertIn('node?node.disabled',page.evaluate.await_args.args[0])

    async def test_categorical_evaluation_error_kept_without_exception_text(self):
        page=types.SimpleNamespace(evaluate=AsyncMock(side_effect=[RuntimeError('Cannot read properties of null SECRET cookie'),
            {'count':1,'present':True,'disabled':False,'phase':'done'}]))
        report={}
        with patch.object(release.asyncio,'sleep',new=AsyncMock()):
            await release.wait_send_release(page,report,lambda:False)
        value=report['send_release_observation']
        self.assertEqual(value['error_counts'],{'NULL_PROPERTY_EVALUATION':1})
        self.assertNotIn('SECRET',json.dumps(value))

    async def test_busy_deadline_remains_hold_without_mutation(self):
        page=types.SimpleNamespace(evaluate=AsyncMock(return_value={'count':1,'present':True,'disabled':True,'phase':'speaking'}))
        report={};times=iter([0,0,10,10,10])
        with patch.object(release,'time',types.SimpleNamespace(monotonic=lambda:next(times))),patch.object(release.asyncio,'sleep',new=AsyncMock()):
            with self.assertRaisesRegex(RuntimeError,'HOLD_QA_SEND_RELEASE_NOT_READY'):
                await release.wait_send_release(page,report,lambda:False)
        self.assertEqual(page.evaluate.await_count,1)
        self.assertEqual(report['send_release_observation']['state'],'HOLD')

    async def test_owner_stop_and_closed_target_do_not_get_retried(self):
        page=types.SimpleNamespace(evaluate=AsyncMock())
        with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            await release.wait_send_release(page,{},lambda:True)
        page.evaluate.assert_not_awaited()
        page.evaluate.side_effect=Exception('Target page, context or browser has been closed SECRET')
        report={}
        with self.assertRaisesRegex(RuntimeError,'HOLD_QA_RELEASE_TARGET_CLOSED'):
            await release.wait_send_release(page,report,lambda:False)
        self.assertNotIn('SECRET',json.dumps(report))
        self.assertEqual(page.evaluate.await_count,1)


class OverlayTests(unittest.TestCase):
    def test_composed_child_preserves_native_entry_and_pins_all_sources(self):
        bundle={name:base64.b64encode(Path(name).read_bytes()).decode() for name in entry.PINS}
        transport_entry=types.ModuleType('frozen_transport_entry_test')
        exec(compile(Path('owner_browser_transport_qa_entry.py').read_bytes(),'<entry>','exec'),transport_entry.__dict__)
        with patch.object(entry,'BUNDLE',bundle):
            blobs=entry.sources();program=entry.child_program(transport_entry.child_program,blobs)
        compile(program,'<release-child>','exec')
        self.assertIn(b'HOLD_BROWSER_RELEASE_CHILD_PIN',program)
        self.assertIn(b'release.install(core,raw,diagnostic',program)
        self.assertIn(b'raise SystemExit(core.main())',program)
        bundle['owner_chat_browser_release_qa.py']=base64.b64encode(b'changed').decode()
        with patch.object(entry,'BUNDLE',bundle),self.assertRaisesRegex(RuntimeError,'BUNDLE_PIN'):
            entry.sources()

    def test_actual_one_prefix_observation_does_not_weaken_original_gate(self):
        core,original=installed()
        value={'native_calls':1,'native_delta_count':149,'ui_before_native_done':True,
            'ui_measurement_kind':'CUMULATIVE_VISIBLE_ASSISTANT_BODY','ui_body_visible':True,
            'dom_answer_matches_native':True,'done':{'saved':True,'s03_integrated':True,'dialog_matches':True},
            'answer_characters':149,'ui_prefix_lengths_before_done':[66],
            'ui_first_ms':5751.5,'native_done_ms':5971.1}
        self.assertTrue(release.two_parts_observed(value))
        self.assertIs(core.progressive_stream_valid,original)
        self.assertFalse(core.progressive_stream_valid(value))
        value['ui_first_ms']=6000
        self.assertFalse(release.two_parts_observed(value))
        code=core.browser_run.__code__
        self.assertIn('_nox_wait_send_release',code.co_names)
        for gate in ('json_response','public_numeric_answer','progressive_stream_valid',
                     'capture_private_screenshot','require_screenshot_captures','_nox_responsive_layout'):
            self.assertIn(gate,code.co_names)
        self.assertEqual(core.EXPECTED,','.join(map(str,range(1,41))))

    def test_changed_dependency_is_not_composed(self):
        with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_PIN'):
            release.install(types.ModuleType('x'),b'changed',types.ModuleType('y'),b'changed')


if __name__=='__main__':unittest.main()
