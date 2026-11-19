"""Portable source/security tests; no browser or native NOX action is executed."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

SPEC=importlib.util.spec_from_file_location('browser_qa',Path(__file__).with_name('owner_chat_browser_qa.py'))
QA=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class BrowserQaTests(unittest.TestCase):
    def test_browser_expected_build_matches_deployed_ui_renderer(self):
        tree = ast.parse(Path(QA.__file__).with_name('owner_chat_ui.py').read_text())
        builds = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'BUILD' for target in node.targets)]
        self.assertEqual(builds, [QA.BUILD])

    def test_resource_paths_never_include_query_credentials(self):
        self.assertEqual(QA.safe_route('http://127.0.0.1:8080/nox-web-v29/owner-chat-ui.js?token=secret'),
                         '/nox-web-v29/owner-chat-ui.js')
        self.assertEqual(QA.safe_route('http://127.0.0.1:8080/api/ui/memory/dialogs/history?dialog_id=private'),
                         '/api/ui/memory/dialogs/history')

    def test_unknown_paths_are_not_exported(self):
        for url in ('http://host/private_customer_name/file','http://host/api/user/alice',
                    'http://host/nox-web-v29/credential.txt','file:///root/nox/secrets/chat_password'):
            self.assertEqual(QA.safe_route(url),'[OTHER_ROUTE]')

    def test_only_known_legacy_static_routes_have_diagnostic_names(self):
        self.assertEqual(QA.safe_route('https://host/pc/v25/nox-shell-v25.css?owner=private'),
                         '/pc/v25/nox-shell-v25.css')
        self.assertEqual(QA.safe_route('https://host/pc/v25/private-dialog.json'), '[OTHER_ROUTE]')

    def test_pointer_projection_keeps_private_text_and_classes_out(self):
        self.assertIn("publicClasses=['nox-v28-pc-return'", QA.CONTROL_JS)
        self.assertIn('elementsFromPoint(x,y).slice(0,6)', QA.CONTROL_JS)
        for forbidden in ('textContent', 'innerHTML', 'outerHTML', 'className', 'getAttribute('):
            self.assertNotIn(forbidden, QA.CONTROL_JS)

    def test_status_projection_does_not_export_model_paths_or_arbitrary_values(self):
        value=QA.status_projection({'model':None,'primary_model':'/private/owner-name/model.gguf',
            'native_p02_bound':True,'backend':'EXISTING_NATIVE_ONEHOST','status':'READY','private':'secret'})
        self.assertTrue(value['primary_model_present']);self.assertFalse(value['legacy_model_truthy'])
        self.assertTrue(value['native_p02_bound']);self.assertTrue(value['native_backend'])
        self.assertTrue(all(type(item) is bool for item in value.values()))

    def test_composer_projection_never_reads_message_or_prompt_content(self):
        self.assertIn('prompt?.value?.length',QA.COMPOSER_JS)
        self.assertNotIn('textContent',QA.COMPOSER_JS)
        self.assertNotIn('innerHTML',QA.COMPOSER_JS)
        self.assertIn("slice(0,2)",QA.COMPOSER_JS)

    def test_report_layout_gate_rejects_original_overflow_or_occluded_composer(self):
        value={'reports_layout':True,'reports':[{'open':True},{'open':True}],
               'status_stack':{'height':280,'overflow_y':'auto'},'viewport_height':1000}
        for name in ('prompt','send'):
            value[name]={'present':True,'visible':True,'fully_in_view':True,'pointer_hit_own_control':True}
        self.assertTrue(QA.composer_layout_valid(value,True))
        for key,problem in [('status_stack',{'height':1932,'overflow_y':'visible'}),
                            ('send',dict(value['send'],fully_in_view=False)),
                            ('prompt',dict(value['prompt'],pointer_hit_own_control=False)),
                            ('reports',[{'open':True},{'open':False}])]:
            changed=copy.deepcopy(value);changed[key]=problem
            self.assertFalse(QA.composer_layout_valid(changed,True))

    def test_only_bounded_public_numbers_can_be_exported(self):
        self.assertEqual(QA.public_numeric_answer('1, 2, 3, 4, 5, 6, 7, 8, 9, 10'),QA.EXPECTED)
        for value in ('owner Alice', 'token=abc', '<img src=x>', '1\nprivate context', '1'*101, None):
            self.assertIsNone(QA.public_numeric_answer(value))

    def test_progressive_gate_requires_two_growing_visible_prefixes_before_done(self):
        value={'ui_measurement_kind':'CUMULATIVE_VISIBLE_ASSISTANT_BODY','native_delta_count':8,
               'ui_before_native_done':True,'ui_prefix_lengths_before_done':[3,5,7],
               'ui_first_ms':90.5,'native_done_ms':200.0}
        self.assertTrue(QA.progressive_stream_valid(value))
        for key,problem in [('ui_prefix_lengths_before_done',[]),
                            ('ui_prefix_lengths_before_done',[3]),
                            ('ui_prefix_lengths_before_done',[3,3]),
                            ('ui_prefix_lengths_before_done',[5,3]),
                            ('ui_prefix_lengths_before_done',[3,True]),
                            ('ui_before_native_done',False),('native_delta_count',1),
                            ('ui_first_ms',201),('ui_measurement_kind','PER_TEXT_NODE')]:
            changed=dict(value);changed[key]=problem
            self.assertFalse(QA.progressive_stream_valid(changed))
        self.assertFalse(QA.progressive_stream_valid(None))

    def test_exception_text_cannot_leak_credentials(self):
        self.assertEqual(QA.safe_error(RuntimeError('password=opaque credential')), 'RuntimeError')
        self.assertEqual(QA.safe_error(RuntimeError('HOLD_OWNER_STOP')), 'HOLD_OWNER_STOP')

    def test_missing_or_unbound_dialog_provider_is_never_accepted_as_s03(self):
        done={'saved':True,'owner_dialog_saved':True,'canonical_s03_write_verified':False,
              'dialog_matches':True,'writer':'V112_OWNER_DIALOG_WRITER',
              'turn_id':'1'*32,'receipt_id':'2'*32,'lease_epoch':'3'*32,
              'exchange_id':'4'*32,'receipt_sha256':'a'*64}
        self.assertFalse(QA.exact_owner_dialog_readback(None,done,'d'*32,'prompt','answer'))
        self.assertFalse(QA.exact_owner_dialog_readback({},done,'d'*32,'prompt','answer'))
        wrong={'status':'READY','durable':True,'verified':True,'store_scope':'OWNER_DIALOG_TABLES_ONLY',
               'canonical_s03_verified':False,'writer':'V112_OWNER_DIALOG_WRITER',
               'dialog_id':'d'*32,'turn_id':'1'*32,'receipt_id':'2'*32,'lease_epoch':'3'*32,
               'exchange_id':'4'*32,'receipt_sha256':'a'*64,
               'messages':[{'role':'user','content':'prompt','exchange_id':'4'*32},
                           {'role':'assistant','content':'different','exchange_id':'4'*32}]}
        self.assertFalse(QA.exact_owner_dialog_readback(wrong,done,'d'*32,'prompt','answer'))
        wrong['messages'][1]['content']='answer'
        self.assertTrue(QA.exact_owner_dialog_readback(wrong,done,'d'*32,'prompt','answer'))
        self.assertFalse(QA.exact_owner_dialog_readback(
            {**wrong,'canonical_s03_verified':True},done,'d'*32,'prompt','answer'))

    def test_runner_requires_two_distinct_sequential_receipt_readbacks(self):
        source=Path(QA.__file__).read_text()
        self.assertIn('QA_TURN_',source)
        self.assertIn('HOLD_OWNER_DIALOG_RECEIPT_AND_INDEPENDENT_READBACK',source)
        self.assertIn('len(verified_turns)!=2',source)
        self.assertIn("len({item['receipt_id'] for item in verified_turns})!=2",source)
        self.assertIn('accepted_submits!=list(prompts)',source)
        self.assertIn("onehost_1a01_acceptance_state='HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND'",source)
        self.assertIn("print('NOX_1A01_CANONICAL_S03_ACCEPTED=false'",source)
        self.assertNotIn("'s03_readback_verified':True",source)
        self.assertNotIn('NOX_MAINT_REPAIR_COMPLETE=true',source)
        self.assertNotIn('route.fulfill(',source)

    def test_click_diagnostic_exports_only_fixed_boolean_flags(self):
        value=QA.click_error_projection(RuntimeError('owner private title: element is not stable; another node intercepts pointer events'))
        self.assertEqual(set(value),{'not_stable','not_visible','outside_viewport','pointer_intercepted','detached'})
        self.assertTrue(value['not_stable']);self.assertTrue(value['pointer_intercepted'])
        self.assertTrue(all(type(flag) is bool for flag in value.values()))

    def test_screenshot_private_creation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'image.png'
            QA.write_private(path,b'public fixture')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):
                QA.write_private(path,b'overwrite')
            self.assertEqual(path.read_bytes(),b'public fixture')

    def test_screenshot_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            real=Path(folder)/'other'
            real.write_bytes(b'preserve')
            link=Path(folder)/'image.png'
            link.symlink_to(real)
            with self.assertRaisesRegex(RuntimeError,'HOLD_BROWSER_ARTIFACT_SYMLINK'):
                QA.write_private(link,b'replace')
            self.assertEqual(real.read_bytes(),b'preserve')

    def test_instrumentation_forwards_real_calls_and_masks_private_regions(self):
        self.assertIn('Reflect.apply(original,this,args)',QA.OBSERVER_JS)
        self.assertIn('const response=await fetch0(input,init)',QA.OBSERVER_JS)
        self.assertIn('observe(response.clone(),t)',QA.OBSERVER_JS)
        self.assertIn('#nativeChats',QA.SENSITIVE_MASKS)
        source=Path(QA.__file__).read_text()
        self.assertNotIn('route.fulfill(',source)
        self.assertNotIn('storage_state(',source)
        self.assertNotIn('base64',source)
        self.assertNotIn('install-deps',source)

    @unittest.skipUnless(shutil.which('node'),'Node unavailable for JS syntax check')
    def test_browser_javascript_parses(self):
        source=(QA.OBSERVER_JS.replace('__CONFIG__','{"did":"'+'a'*32+'"}')
                +'\nconst snapshot=('+QA.SNAPSHOT_JS+');\nconst control=('+QA.CONTROL_JS+');\n'
                +'const composer=('+QA.COMPOSER_JS+');\n')
        result=subprocess.run([shutil.which('node'),'--check'],input=source,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


class SendPointerTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, *, native_calls=0, hit=True, enabled=True):
        target=types.SimpleNamespace(evaluate=AsyncMock(return_value={'x':100,'y':150,'in_view':True,
            'pointer_hit_own_button':hit}), click=AsyncMock(side_effect=TimeoutError('timed out')),
            is_enabled=AsyncMock(return_value=enabled))
        page=types.SimpleNamespace(locator=lambda _:target,
            evaluate=AsyncMock(return_value={'native_calls':native_calls}),
            mouse=types.SimpleNamespace(click=AsyncMock()))
        return page,target,{}

    async def test_actual_pointer_fallback_requires_fresh_own_hit_and_enabled(self):
        page,target,report=self.fixture()
        await QA.click_send(page,report)
        page.mouse.click.assert_awaited_once_with(100,150)
        self.assertEqual(target.evaluate.await_count,2)
        self.assertTrue(report['qa_send_control']['physical_pointer_click'])

    async def test_already_started_native_request_is_never_clicked_again(self):
        page,target,report=self.fixture(native_calls=1,enabled=False)
        await QA.click_send(page,report)
        page.mouse.click.assert_not_awaited()
        self.assertTrue(report['qa_send_control']['native_request_already_started'])

    async def test_occlusion_disabled_or_unknown_request_state_is_not_bypassed(self):
        for options in ({'hit':False},{'enabled':False},{'native_calls':None},{'native_calls':2}):
            page,_,report=self.fixture(**options)
            with self.assertRaisesRegex(RuntimeError,'HOLD_QA_SEND_POINTER_OR_STATE'):
                await QA.click_send(page,report)
            page.mouse.click.assert_not_awaited()


class ScreenshotTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_timeout_allows_send_but_never_full_visual_acceptance(self):
        class DriverTimeout(Exception):
            pass
        target=types.SimpleNamespace(evaluate=AsyncMock(return_value={'in_view':True,
            'pointer_hit_own_button':True}),click=AsyncMock())
        page=types.SimpleNamespace(
            screenshot=AsyncMock(side_effect=DriverTimeout('private title; waiting for fonts to load')),
            locator=lambda _:target)
        report={'artifacts':[]};masks=[object(),object()]
        with tempfile.TemporaryDirectory() as folder,patch.object(QA,'stop_present',return_value=False):
            result=await QA.capture_private_screenshot(page,report,Path(folder),'empty',masks,
                'EMPTY_QA_VIEW_WITH_PRIVACY_MASKS',(TimeoutError,DriverTimeout))
            self.assertFalse(result)
            self.assertEqual(list(Path(folder).iterdir()),[])
            self.assertIs(page.screenshot.await_args.kwargs['mask'],masks)
            self.assertEqual(page.screenshot.await_args.kwargs['timeout'],3500)
            # The same physical-send helper used next by browser_run remains
            # reachable after the capture timed out; no model response is faked.
            await QA.click_send(page,report)
            target.click.assert_awaited_once()
            with self.assertRaisesRegex(RuntimeError,'HOLD_SCREENSHOT_CAPTURE_PENDING'):
                QA.require_screenshot_captures(report)
        self.assertFalse(report['screenshot_capture_verified'])
        self.assertEqual(report['screenshot_captures'][0]['state'],'CAPTURE_TIMEOUT')
        self.assertTrue(report['screenshot_captures'][0]['font_wait_reported'])
        self.assertNotIn('private title',json.dumps(report))

    async def test_non_timeout_capture_failure_is_not_deferred(self):
        page=types.SimpleNamespace(screenshot=AsyncMock(side_effect=RuntimeError('capture failed')))
        with tempfile.TemporaryDirectory() as folder,patch.object(QA,'stop_present',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'capture failed'):
                await QA.capture_private_screenshot(page,{'artifacts':[]},Path(folder),'empty',[],
                    'EMPTY_QA_VIEW_WITH_PRIVACY_MASKS')

    async def test_two_private_captures_are_required_and_preserve_masks(self):
        page=types.SimpleNamespace(screenshot=AsyncMock(return_value=b'private screenshot fixture'))
        report={'artifacts':[]};masks=[object()]
        with tempfile.TemporaryDirectory() as folder,patch.object(QA,'stop_present',return_value=False):
            for name in ('empty','completed'):
                self.assertTrue(await QA.capture_private_screenshot(page,report,Path(folder),name,masks,
                    'EMPTY_QA_VIEW_WITH_PRIVACY_MASKS'))
                self.assertEqual(stat.S_IMODE((Path(folder)/(name+'.png')).stat().st_mode),0o600)
            QA.require_screenshot_captures(report)
            self.assertTrue(report['screenshot_capture_verified'])
            self.assertTrue(all(call.kwargs['mask'] is masks for call in page.screenshot.await_args_list))


class IdleSlotsTests(unittest.TestCase):
    def run_gate(self, values, stop=lambda:False):
        clock=[0.0];calls=[]
        class Response:
            def __init__(self,value):self.value=value
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,limit):return json.dumps(self.value).encode()
        def opening(url,timeout):
            calls.append((url,timeout))
            value=values[min(len(calls)-1,len(values)-1)]
            return Response(value)
        with patch.object(QA.urllib.request,'build_opener',return_value=types.SimpleNamespace(open=opening)), \
             patch.object(QA,'stop_present',side_effect=stop), \
             patch.object(QA.time,'monotonic',side_effect=lambda:clock[0]), \
             patch.object(QA.time,'sleep',side_effect=lambda duration:clock.__setitem__(0,clock[0]+duration)):
            return QA.idle_slots(),calls,clock[0]

    def test_short_foreground_request_is_waited_out_without_sending_inference(self):
        count,calls,elapsed=self.run_gate([[{'is_processing':True}],[{'is_processing':False}]*6])
        self.assertEqual(count,6);self.assertEqual(elapsed,1)
        self.assertEqual([url for url,_ in calls],['http://127.0.0.1:8081/slots']*2)
        self.assertTrue(all(0<timeout<=4 for _,timeout in calls))

    def test_persistent_busy_is_not_bypassed_at_deadline(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_FOREGROUND_CHAT_BUSY'):
            self.run_gate([[{'is_processing':True}]])

    def test_missing_string_or_conflicting_processing_flags_never_mean_idle(self):
        for value in ([{}],[{'is_processing':'false'}],[{'processing':0}],
                      [{'is_processing':False,'processing':True}],[],{}):
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'HOLD_SLOTS_STATE_UNVERIFIED'):
                self.run_gate([value])

    def test_stop_during_wait_is_respected_before_next_request(self):
        checks=[False,False,True]
        def stopped():return checks.pop(0) if checks else True
        with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            self.run_gate([[{'is_processing':True}],[{'is_processing':False}]],stopped)

    def test_stop_arriving_during_idle_read_still_blocks_acceptance(self):
        checks=[False,True]
        with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            self.run_gate([[{'is_processing':False}]],lambda:checks.pop(0))


if __name__=='__main__':
    unittest.main()
