"""A6 responsive browser composer contract, source-only and no native POST."""
import hashlib
import unittest
from io import BytesIO
from urllib.error import URLError
from unittest.mock import patch
from owner_chat_browser_qa import (COMPOSER_JS, RESPONSIVE_LAYOUT_CASES,
    allowed_qa_request, fresh_qa_post_admission, post_admission_hold_reason,
    browser_route_method_allowed, check_report_layout, click_send, verify_saved_browser_refresh,
    idle_slots, MODEL_SLOTS_URL, pinned_served_html_hash,
    native_stream_envelope_valid, progressive_stream_valid, canonical_s03_proof_valid, OBSERVER_JS, SNAPSHOT_JS)

class FakePage:
    def __init__(self, bad_width=None, reported_width=None, reported_height=None):
        self.size = None
        self.views = []
        self.bad_width = bad_width
        self.reported_width = reported_width
        self.reported_height = reported_height
        self.opened = False
    async def set_viewport_size(self, size):
        self.size = dict(size)
        self.views.append((size["width"], size["height"]))
    async def evaluate(self, script, opened=None):
        if 'for(const node of document.querySelectorAll' in script:
            self.opened = opened
            return None
        if script == COMPOSER_JS:
            width, height = self.size["width"], self.size["height"]
            control = {"present":True,"visible":True,"fully_in_view":True,
                       "pointer_hit_own_control":True}
            if width == self.bad_width:
                control = dict(control, pointer_hit_own_control=False)
            return {"reports_layout":True, "reports":[{"open":self.opened},{"open":self.opened}],
                    "status_stack":{"overflow_y":"auto","height":min(180,height/5)},
                    "viewport_width":self.reported_width if self.reported_width is not None else width,
                    "viewport_height":self.reported_height if self.reported_height is not None else height,
                    "prompt":dict(control),"send":dict(control)}
        if "report_scroll_verified" in script:
            return True
        if "node.scrollTop=stack.scrollHeight" in script:
            return True
        # Pre-layout reflow or bounded-scroll check.
        if "node.scrollTop=node.scrollHeight" in script:
            return True
        return None

class ResponsiveComposerContract(unittest.IsolatedAsyncioTestCase):
    async def test_real_probe_includes_mobile_tablet_desktop_and_restores_desktop(self):
        page=FakePage()
        report={}
        await check_report_layout(page,report)
        self.assertTrue({320,390,800,1024,1280,1440}.issubset({w for w,h in page.views}))
        self.assertEqual(page.views[-1],(1440,1000))
        self.assertEqual(len(page.views),len(RESPONSIVE_LAYOUT_CASES))
        self.assertEqual(len(report["report_layout_cases"]),len(RESPONSIVE_LAYOUT_CASES))
        self.assertTrue(report["report_scroll_verified"])

    async def test_stale_viewport_width_or_height_must_hold_before_chat(self):
        # set_viewport_size can succeed while the page still reports a stale
        # 1440x1000 layout; a desktop-only layout must never pass mobile QA.
        for stale in ({"reported_width":1440},{"reported_height":1000}):
            with self.subTest(stale=stale):
                page=FakePage(**stale)
                with self.assertRaisesRegex(RuntimeError,"HOLD_QA_REPORTS_COMPOSER_LAYOUT"):
                    await check_report_layout(page,{})
                self.assertEqual(page.views[-1],(320,720))

    async def test_mobile_occluded_send_must_hold(self):
        page=FakePage(bad_width=320)
        with self.assertRaisesRegex(RuntimeError,"HOLD_QA_REPORTS_COMPOSER_LAYOUT"):
            await check_report_layout(page,{})
        self.assertIn((320,720),page.views)



class CanonicalTwoTurnS03EvidenceContract(unittest.TestCase):
    def test_single_turn_or_broken_roles_cannot_pass_canonical_readback(self):
        dialog = 'scoped-dialog'
        rows = [{'role': 'user', 'content': 'First prompt'},
                {'role': 'assistant', 'content': 'First response'},
                {'role': 'user', 'content': 'Follow-up'},
                {'role': 'assistant', 'content': 'Second response'}]
        receipt = {'source': 'canonical_s03', 'verified': True, 'durable': True,
                   'event_id': 'event-2', 'turn_id': 'turn-2',
                   'sequence': 2, 'dialog_id': dialog}
        def readback(messages):
            answer = messages[-1].get('content', '') if messages and isinstance(messages[-1], dict) else ''
            return {'source': 'canonical_s03', 'independent': True,
                    'event_id': 'event-2', 'turn_id': 'turn-2',
                    'sequence': 2, 'dialog_id': dialog,
                    'messages': messages,
                    'full_answer_sha256': hashlib.sha256(str(answer).encode()).hexdigest()}
        self.assertTrue(canonical_s03_proof_valid(receipt, readback(rows), dialog, rows))
        invalid = [
            rows[-1:],  # Prior code admitted single assistant as canonical two-turn.
            rows[:2],   # One exchange is not multi-turn.
            [dict(r) for r in rows[:3]] + [{'role': 'user', 'content': 'Wrong'}],
            [dict(r) for r in rows[:3]] + [{'role': 'assistant', 'content': ''}],
            [dict(r) for r in rows[:3]] + [{'role': 'assistant', 'content': 123}],
            [dict(r) for r in rows[:3]] + [None],
        ]
        for case in invalid:
            with self.subTest(case=repr(case)[-80:]):
                self.assertFalse(canonical_s03_proof_valid(receipt, readback(case), dialog, case))


class ProgressiveStreamEvidenceContract(unittest.TestCase):
    def test_progress_must_be_finite_and_bounded_by_real_native_answer(self):
        good = {'ui_measurement_kind':'CUMULATIVE_VISIBLE_ASSISTANT_BODY',
                'native_delta_count':2,'ui_before_native_done':True,
                'ui_prefix_lengths_before_done':[3,5],
                'answer_characters':8,'ui_first_ms':12.0,'native_done_ms':28.0}
        self.assertTrue(progressive_stream_valid(good))
        for field, bad in (
            ('answer_characters', 4),  # Claimed visible prefix exceeds model answer.
            ('answer_characters', None),
            ('answer_characters', True),
            ('answer_characters', 4097),
            ('ui_first_ms', float('nan')),
            ('native_done_ms', float('inf')),
            ('native_done_ms', 10**500),
        ):
            with self.subTest(field=field, bad=str(bad)[:24]):
                self.assertFalse(progressive_stream_valid(dict(good, **{field:bad})))


class SavedRefreshContract(unittest.IsolatedAsyncioTestCase):
    async def test_one_reload_requires_saved_answer_and_zero_new_native_posts(self):
        html=b'<html>trusted saved page</html>'
        sha=hashlib.sha256(html).hexdigest()

        class Response:
            status=200
            async def body(self):
                return html

        class Target:
            first=None
            def __init__(self):
                self.first=self
            def filter(self, has=None):
                return self
            async def count(self):
                return 1
            async def get_attribute(self, name):
                return 'true'
            async def click(self, timeout=0):
                raise AssertionError('Previously selected dialog must not be re-clicked')

        class Page:
            url='http://127.0.0.1:18877/nox-web-v29/pc/resonance.html'
            def __init__(self, native_calls):
                self.native_calls=native_calls
                self.reloads=0
                self.target=Target()
            async def reload(self, **kwargs):
                self.reloads+=1
                return Response()
            async def wait_for_function(self, *args, **kwargs):
                return None
            def locator(self, selector):
                return self.target
            def get_by_text(self, *args, **kwargs):
                return self.target
            async def evaluate(self, script):
                return {'native_calls':self.native_calls} if script==SNAPSHOT_JS else False

        page=Page(0)
        report={}
        await verify_saved_browser_refresh(page,report,'synthetic QA','1,2,3',sha)
        self.assertEqual(page.reloads,1)
        self.assertTrue(report['browser_refresh_persisted'])
        second=Page(1)
        with self.assertRaisesRegex(RuntimeError,'HOLD_QA_REFRESH_DUPLICATE_NATIVE_POST'):
            await verify_saved_browser_refresh(second,{},'synthetic QA','1,2,3',sha)
        self.assertEqual(second.reloads,1)

class AmbiguousSendContract(unittest.IsolatedAsyncioTestCase):
    @patch('owner_chat_browser_qa.stop_present',return_value=False)
    async def test_unknown_click_delivery_must_not_be_retried(self, _stop_present):
        class Target:
            def __init__(self):
                self.clicks=0
            async def evaluate(self, javascript):
                return {"in_view": True, "pointer_hit_own_button": True, "x": 10, "y": 20}
            async def click(self, timeout):
                self.clicks+=1
                raise RuntimeError("click timeout after possibly delivered pointer")

        class Page:
            def __init__(self, native_calls):
                self.target=Target()
                self.native_calls=native_calls
                self.fallback_clicks=0
                self.mouse=self
            def locator(self, selector):
                return self.target
            async def evaluate(self, script):
                return {"native_calls": self.native_calls}
            async def click(self, x, y):
                self.fallback_clicks+=1

        for count in (0, None, 2):
            with self.subTest(native_calls=count):
                page=Page(count)
                report={}
                with self.assertRaisesRegex(RuntimeError,"HOLD_QA_SEND_CLICK_DELIVERY_UNKNOWN"):
                    await click_send(page,report,expected_before=0)
                self.assertEqual(page.target.clicks,1)
                self.assertEqual(page.fallback_clicks,0)
                self.assertTrue(report["qa_send_control"]["click_wait"])
        page=Page(1)
        await click_send(page,{},expected_before=0)
        self.assertEqual(page.target.clicks,1)
        self.assertEqual(page.fallback_clicks,0)

class OwnerStopBeforePostContract(unittest.IsolatedAsyncioTestCase):
    async def test_late_owner_stop_vetoes_send_click_and_route_admission(self):
        class Target:
            def __init__(self):
                self.clicks=0
            async def evaluate(self, javascript):
                return {"present":True,"in_view":True,"pointer_hit_own_button":True}
            async def click(self, timeout):
                self.clicks+=1
        class Page:
            def __init__(self):
                self.target=Target()
            def locator(self, selector):
                return self.target
        body={"message":"synthetic", "dialog_id":"qa-id"}
        args=(0,False,"synthetic","next",body,"qa-id")
        self.assertTrue(allowed_qa_request(*args,owner_stopped=False))
        self.assertFalse(allowed_qa_request(*args,owner_stopped=True))
        # Treat an unknown stop observation as non-admission too.
        self.assertFalse(allowed_qa_request(*args,owner_stopped=None))
        page=Page()
        with patch('owner_chat_browser_qa.stop_present',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
                await click_send(page,{},expected_before=0)
        self.assertEqual(page.target.clicks,0)


class OwnerResourceBeforePostContract(unittest.TestCase):
    def test_resource_drift_and_stop_must_veto_each_native_post(self):
        args=(0,False,'synthetic','next',
              {'message':'synthetic','dialog_id':'qa-id'},'qa-id')
        with patch('owner_chat_browser_qa.stop_present',return_value=False), \
             patch('owner_chat_browser_qa.budget',return_value={'checked':True}) as read:
            self.assertTrue(fresh_qa_post_admission(*args))
            read.assert_called_once_with()
        with patch('owner_chat_browser_qa.stop_present',return_value=False), \
             patch('owner_chat_browser_qa.budget',side_effect=RuntimeError('HOLD_BROWSER_RAM_RESERVE')) as read:
            with self.assertRaisesRegex(RuntimeError,'HOLD_BROWSER_RAM_RESERVE'):
                fresh_qa_post_admission(*args)
            read.assert_called_once_with()
        with patch('owner_chat_browser_qa.stop_present',return_value=True), \
             patch('owner_chat_browser_qa.budget') as read:
            self.assertFalse(fresh_qa_post_admission(*args))
            read.assert_not_called()
        with patch('owner_chat_browser_qa.stop_present',side_effect=[False,True]), \
             patch('owner_chat_browser_qa.budget',return_value={'checked':True}) as read:
            self.assertFalse(fresh_qa_post_admission(*args))
            read.assert_called_once_with()

    def test_slot_and_foreground_hold_reasons_are_not_lost(self):
        # This is the reason recorded by the actual route guard; a dropped
        # reason used to wait up to 85 s and report an unrelated stream HOLD.
        for reason in ('HOLD_FOREGROUND_CHAT_BUSY','HOLD_SLOTS_RESPONSE_LIMIT',
                       'HOLD_SLOTS_STATE_UNVERIFIED','HOLD_SLOTS_ENDPOINT_UNAVAILABLE',
                       'HOLD_BROWSER_RAM_RESERVE',
                       'HOLD_OWNER_STOP'):
            with self.subTest(reason=reason):
                self.assertEqual(post_admission_hold_reason(RuntimeError(reason)),reason)
        self.assertIsNone(post_admission_hold_reason(RuntimeError('credential or endpoint detail')))
        self.assertIsNone(post_admission_hold_reason(RuntimeError('HOLD_BAD:leaked-detail')))

class OwnerModelSlotsPortContract(unittest.TestCase):
    def test_pinned_model_slot_endpoint_is_read_only_and_fail_closed(self):
        self.assertEqual(MODEL_SLOTS_URL, 'http://127.0.0.1:8098/slots')
        class Opener:
            def __init__(self, payload=None, error=None):
                self.payload, self.error = payload, error
                self.calls = []
            def open(self, url, timeout):
                self.calls.append((url, timeout))
                if self.error:
                    raise self.error
                return BytesIO(self.payload)
        ready = Opener(b'[{"is_processing": false}]')
        with patch('owner_chat_browser_qa.stop_present', return_value=False), \
             patch('owner_chat_browser_qa.urllib.request.build_opener', return_value=ready):
            self.assertEqual(idle_slots(), 1)
        self.assertEqual(len(ready.calls), 1)
        self.assertEqual(ready.calls[0][0], MODEL_SLOTS_URL)
        self.assertGreater(ready.calls[0][1], 0)
        for opener, reason in (
            (Opener(error=URLError('connection refused')), 'HOLD_SLOTS_ENDPOINT_UNAVAILABLE'),
            (Opener(payload=b'{not-json'), 'HOLD_SLOTS_STATE_UNVERIFIED'),
            (Opener(payload=b'[{"is_processing": "no"}]'), 'HOLD_SLOTS_STATE_UNVERIFIED'),
        ):
            with self.subTest(reason=reason):
                with patch('owner_chat_browser_qa.stop_present', return_value=False), \
                     patch('owner_chat_browser_qa.urllib.request.build_opener', return_value=opener):
                    with self.assertRaisesRegex(RuntimeError, reason):
                        idle_slots()
                self.assertEqual(len(opener.calls), 1)


class ServedHtmlPinContract(unittest.TestCase):
    def test_exact_response_bytes_required_not_just_meta_build_marker(self):
        # Equal build markers do not prove equal served bytes.
        authentic = b'<html><meta name="nox-live-build" content="NOX_OWNER_LIVE_RESONANCE_20261116"></html>'
        tampered = b'<html><meta name="nox-live-build" content="NOX_OWNER_LIVE_RESONANCE_20261116"><!-- stale --></html>'
        sha = hashlib.sha256(authentic).hexdigest()
        self.assertEqual(pinned_served_html_hash(sha, authentic), sha)
        with self.assertRaisesRegex(RuntimeError, 'HOLD_SERVED_HTML_SHA256_MISMATCH'):
            pinned_served_html_hash(sha, tampered)
        for pin in (None, '', '1234', sha.upper(), b'1' * 64):
            with self.subTest(pin=pin):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_SERVED_HTML_SHA256_PIN_MISSING'):
                    pinned_served_html_hash(pin, authentic)
        for data in (None, '', b''):
            with self.subTest(data_type=type(data).__name__):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_SERVED_HTML_BYTES_UNVERIFIED'):
                    pinned_served_html_hash(sha, data)
        with self.assertRaisesRegex(RuntimeError, 'HOLD_SERVED_HTML_BYTES_LIMIT'):
            pinned_served_html_hash(sha, b'x' * (8 * 1024 * 1024 + 1))


class NativeStreamTerminalEnvelopeContract(unittest.TestCase):
    def test_terminal_flag_does_not_suffice_without_physical_eof(self):
        # Both first/second browser turns must observe the complete response
        # body, exactly one terminal frame and no parser error before PASS.
        done = {'saved': True, 's03_integrated': True, 'dialog_matches': True}
        proof = {'native_closed': True, 'native_terminals': 1,
                 'done': done, 'error': None}
        self.assertTrue(native_stream_envelope_valid(proof))
        for changed in (
            {'native_closed': False},
            {'native_closed': None},
            {'native_terminals': 0},
            {'native_terminals': 2},
            {'native_terminals': True},
            {'done': None},
            {'done': {}},
            {'done': {'saved': True}},
            {'done': {'saved': True, 's03_integrated': True}},
            {'done': {'saved': 1, 's03_integrated': True, 'dialog_matches': True}},
            {'done': {'saved': True, 's03_integrated': False, 'dialog_matches': True}},
            {'done': {'saved': True, 's03_integrated': True, 'dialog_matches': False}},
            {'error': 'HOLD_QA_STREAM_PARTIAL_FRAME'},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(native_stream_envelope_valid(dict(proof, **changed)))
        self.assertFalse(native_stream_envelope_valid(None))
        # Keep the live browser fetch observer wired to the same fail-closed
        # proof; an offline Python helper by itself cannot establish wire EOF.
        for guard in (
            "if(part.done){reachedEof=true;break;}",
            "if(q.done!==null)throw Error('HOLD_QA_STREAM_AFTER_DONE')",
            "if(!reachedEof)throw Error('HOLD_QA_STREAM_CHUNK_LIMIT')",
            "if(buffer.trim())throw Error('HOLD_QA_STREAM_PARTIAL_FRAME')",
            "if(q.nativeTerminals!==1)throw Error('HOLD_QA_STREAM_TERMINAL_MISSING')",
            "q.nativeClosed=true",
        ):
            self.assertIn(guard, OBSERVER_JS)
        # The final browser snapshot is built by a separate JS function.
        self.assertIn("native_closed:q.nativeClosed,native_terminals:q.nativeTerminals",
                      SNAPSHOT_JS)


class BrowserWriteScopeContract(unittest.TestCase):
    def test_no_implicit_browser_write_outside_scoped_model_stream(self):
        # Browser page fetches may read UI/static data, but only the exact
        # owner-guarded stream POST may reach the server from the page.
        for path in ('/', '/nox-web-v29/pc/resonance.html',
                     '/api/ui/memory/dialogs/history', '/api/nox/status'):
            with self.subTest(method='GET', path=path):
                self.assertTrue(browser_route_method_allowed('GET', path))
        self.assertTrue(browser_route_method_allowed('HEAD', '/api/nox/status'))
        # Unknown same-origin GET API endpoints may be legacy mutators.
        # Do not accidentally count a QA pass after their side effects.
        for path in ('/api/nox/chat/stream', '/api/ui/memory/dialogs',
                     '/api/ui/memory/dialogs/history', '/chat/session'):
            self.assertTrue(browser_route_method_allowed('GET', path))
        for path in ('/admin/restart', '/runner/reboot', '/actions/flush',
                     '/.env', '/api/admin/shutdown', '/api/ui/memory/dialogs/delete',
                     '/chat/session/revoke', '/api%2Fnox%2Fstop',
                     '/%61pi/nox/stop', '/api/nox/status%2Fdelete',
                     '/api', '/nox', '/nox/chat', '//api/nox/stop',
                     '/ui//api/nox/stop', '/ui/../api/nox/stop',
                     '/ui/./api/nox/stop'):
            for method in ('GET', 'HEAD'):
                with self.subTest(method=method, path=path):
                    self.assertFalse(browser_route_method_allowed(method, path))
        self.assertTrue(browser_route_method_allowed('GET', '/nox-web-v29/pc/resonance.html'))
        self.assertTrue(browser_route_method_allowed('GET', '/pc/v25/nox-shell-v25.css'))
        self.assertTrue(browser_route_method_allowed('HEAD', '/nox-web-v29/pc/resonance.html'))
        self.assertTrue(browser_route_method_allowed('POST', '/api/nox/chat/stream'))
        # A GET/HEAD sent to an action route must not bypass the write fence:
        # old policy admitted every read-like method regardless of path.
        for path in ('/api/nox/stop', '/chat/logout', '/chat/login',
                     '/api/ui/memory/dialogs/create'):
            for method in ('GET', 'HEAD'):
                with self.subTest(method=method, path=path):
                    self.assertFalse(browser_route_method_allowed(method, path))
        for method,path in (
                ('POST', '/api/nox/chat'), ('POST', '/nox/chat'),
                ('POST', '/api/ui/memory/dialogs/create'),
                ('POST', '/api/nox/stop'), ('POST', '/chat/login'),
                ('PUT', '/api/nox/chat/stream'),
                ('PATCH', '/api/nox/chat/stream'),
                ('DELETE', '/api/ui/memory/dialogs/history'),
                ('OPTIONS', '/api/nox/chat/stream')):
            with self.subTest(method=method, path=path):
                self.assertFalse(browser_route_method_allowed(method, path))


if __name__=="__main__":
    unittest.main()
