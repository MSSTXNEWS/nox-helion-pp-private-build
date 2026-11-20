"""Check meaningful streaming timing and synthetic-only evidence boundaries."""
import importlib.util
import json
import urllib.request
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).with_name('owner_chat_probe.py')
spec = importlib.util.spec_from_file_location('owner_probe_test', path)
probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)


class SyntheticBoundedReader:
    """Offline response fixture: expose the bounded readline API of HTTPResponse."""
    url = 'http://127.0.0.1:8080/api/nox/chat/stream'
    def readline(self, limit):
        if not hasattr(self, '_line_stream'):
            self._line_stream = iter(self)
        try:
            return next(self._line_stream)[:limit]
        except StopIteration:
            return b''


class ProbeTests(unittest.TestCase):
    def test_cgroup_ram_admission_precedes_synthetic_dialog_or_chat_post(self):
        """No synthetic write when cgroup-v2 counters are absent or below 2 GiB."""
        threshold = 2 * 1024 ** 3
        with TemporaryDirectory() as directory:
            maximum = Path(directory) / 'memory.max'
            current = Path(directory) / 'memory.current'
            maximum.write_text(str(4 * threshold))
            current.write_text(str(3 * threshold))
            self.assertEqual(
                probe.require_cgroup_probe_headroom(maximum, current, threshold),
                threshold)
            current.write_text(str(3 * threshold + 1))
            with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_CGROUP_RAM_ADMISSION'):
                probe.require_cgroup_probe_headroom(maximum, current, threshold)
            for total, used in (('max', '0'), ('not-a-number', '0'),
                                ('5', '6'), ('0', '0'), ('20', '-1')):
                with self.subTest(maximum=total, current=used):
                    maximum.write_text(total)
                    current.write_text(used)
                    with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_CGROUP_RAM_ADMISSION'):
                        probe.require_cgroup_probe_headroom(maximum, current, threshold)
            current.unlink()
            with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_CGROUP_RAM_ADMISSION'):
                probe.require_cgroup_probe_headroom(maximum, current, threshold)
        source = path.read_text()
        self.assertLess(
            source.index('require_cgroup_probe_headroom()  # Before ANY synthetic dialog-create/chat POST.'),
            source.index("dialog=obj(request(client,'/api/ui/memory/dialogs/create'"))

    def test_each_synthetic_stream_turn_rechecks_cgroup_before_post(self):
        """An accepted first turn cannot authorize a later POST after RAM drops."""
        did = '1' * 32
        with patch.object(probe, 'require_cgroup_probe_headroom',
                          side_effect=[3 * 1024 ** 3, 3 * 1024 ** 3,
                                       RuntimeError('HOLD_CHAT_PROBE_CGROUP_RAM_ADMISSION')]) as gate, \
             patch.object(probe, 'consume_turn', return_value={'answer': '323'}) as stream:
            self.assertEqual(probe.admitted_consume_turn('client', 'first', did)['answer'], '323')
            self.assertEqual(probe.admitted_consume_turn('client', 'second', did)['answer'], '323')
            with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_PROBE_CGROUP_RAM_ADMISSION$'):
                probe.admitted_consume_turn('client', 'third', did, timeout=30)
            self.assertEqual(gate.call_count, 3)
            self.assertEqual(stream.call_count, 2)
            self.assertEqual(stream.call_args_list[0].args[:3], ('client', 'first', did))
            self.assertEqual(stream.call_args_list[1].args[:3], ('client', 'second', did))
        source = path.read_text()
        # All three real main() stream call sites must pass the admission gate.
        self.assertIn("turn=admitted_consume_turn(client,prompt,did)", source)
        self.assertIn("follow=admitted_consume_turn(client,followup,did)", source)
        self.assertIn("turn3=admitted_consume_turn(client,question,did,timeout=30)", source)
        self.assertNotIn("turn=consume_turn(client,prompt,did)", source)
        self.assertNotIn("follow=consume_turn(client,followup,did)", source)
        self.assertNotIn("turn3=consume_turn(client,question,did", source)

    def test_chat_post_redirect_is_never_replayed_to_a_different_url(self):
        """A POST must stop at any redirect, before the final URL checks."""
        handler = probe.RejectPostRedirect()
        source_url = 'http://127.0.0.1:8080/api/nox/chat/stream'
        foreign_url = 'http://other.example/collect'
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                posted = urllib.request.Request(
                    source_url, data=b'{"message":"synthetic"}', method='POST')
                self.assertIsNone(handler.redirect_request(
                    posted, None, code, 'redirect', {}, foreign_url))
        get = urllib.request.Request(source_url, method='GET')
        same_origin = 'http://127.0.0.1:8080/login'
        redirected = handler.redirect_request(
            get, None, 302, 'redirect', {}, same_origin)
        self.assertEqual(redirected.get_method(), 'GET')
        self.assertEqual(redirected.full_url, same_origin)
        source = path.read_text()
        self.assertIn('RejectPostRedirect())', source)
        self.assertEqual(source.count('class RejectPostRedirect('), 1)

    def test_chat_stream_final_url_cannot_redirect_or_switch_model_route(self):
        class Response:
            status = 200
            def __init__(self, url):
                self.url = url
                self.closed = False
                self.read_called = False
            def close(self):
                self.closed = True
            def readline(self, limit):
                self.read_called = True
                raise AssertionError('Untrusted endpoint must not be parsed')

        route = 'http://127.0.0.1:8080/api/nox/chat/stream'
        with patch.object(probe, 'BASE', 'http://127.0.0.1:8080'):
            self.assertIsNone(probe.require_exact_stream_target(Response(route)))
            for target, hold in (
                ('http://127.0.0.1:8080/chat/login', 'HOLD_STREAM_RESPONSE_REDIRECT'),
                (route + '?model=other', 'HOLD_STREAM_RESPONSE_REDIRECT'),
                ('http://127.0.0.1:8080/api/nox/chat', 'HOLD_STREAM_RESPONSE_REDIRECT'),
                ('http://other.example/api/nox/chat/stream', 'HOLD_STREAM_RESPONSE_ORIGIN'),
                ('https://127.0.0.1:8080/api/nox/chat/stream', 'HOLD_STREAM_RESPONSE_ORIGIN'),
            ):
                response = Response(target)
                with self.subTest(target=target), patch.object(probe, 'request', return_value=response) as http:
                    with self.assertRaisesRegex(RuntimeError, '^' + hold + '$'):
                        probe.consume_turn(object(), 'synthetic', '1' * 32)
                    http.assert_called_once()
                self.assertFalse(response.read_called)
                self.assertTrue(response.closed)
        source = path.read_text()
        self.assertIn('require_exact_stream_target(response)', source)

    def test_stream_line_read_is_bounded_before_untrusted_json_parse(self):
        class Oversize:
            status = 200
            url = 'http://127.0.0.1:8080/api/nox/chat/stream'
            def __init__(self): self.closed = False; self.read_sizes = []
            def close(self): self.closed = True
            def readline(self, limit):
                self.read_sizes.append(limit)
                return b' ' * limit

        oversized = Oversize()
        with patch.object(probe, 'request', return_value=oversized):
            with self.assertRaisesRegex(RuntimeError, '^HOLD_BOUNDED_STREAM$'):
                probe.consume_turn(object(), 'synthetic', '1' * 32)
        self.assertEqual(oversized.read_sizes, [100001])
        self.assertTrue(oversized.closed)

        class NoReadline:
            status = 200
            url = 'http://127.0.0.1:8080/api/nox/chat/stream'
            def __init__(self): self.closed = False
            def close(self): self.closed = True
            def __iter__(self):
                raise AssertionError('Unsafe fallback iteration must not run')

        missing = NoReadline()
        with patch.object(probe, 'request', return_value=missing):
            with self.assertRaisesRegex(RuntimeError, '^HOLD_STREAM_BOUNDED_READER_UNAVAILABLE$'):
                probe.consume_turn(object(), 'synthetic', '1' * 32)
        self.assertTrue(missing.closed)
        source = path.read_text()
        self.assertIn('for index,line in enumerate(bounded_stream_lines(response)):', source)
        self.assertIn('readline(max_line + 1)', source)


    def test_html_page_snapshot_bounded_closes_on_all_paths(self):
        class Response:
            def __init__(self, status=200, body=b'<html>ok</html>', interrupted=False):
                self.status, self.body = status, body
                self.url = 'http://127.0.0.1:8080/nox-web-v29/chat.html?secret=not-exported'
                self.interrupted, self.closed, self.requested_size = interrupted, False, None
            def read(self, size):
                self.requested_size = size
                if self.interrupted:
                    raise OSError('synthetic-read-failure')
                return self.body[:size]
            def close(self):
                self.closed = True

        ok = Response()
        status, path, raw = probe.page_snapshot(ok, limit=100)
        self.assertEqual((status, path, raw), (200, '/nox-web-v29/chat.html', b'<html>ok</html>'))
        self.assertEqual(ok.requested_size, 101)
        self.assertTrue(ok.closed)
        unauth = Response(status=401, body=b'Unauthorized')
        self.assertEqual(probe.page_snapshot(unauth, limit=100)[0], 401)
        self.assertTrue(unauth.closed)
        oversized = Response(body=b'x' * 8)
        with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_PAGE_LIMIT$'):
            probe.page_snapshot(oversized, limit=7)
        self.assertEqual(oversized.requested_size, 8)
        self.assertTrue(oversized.closed)
        interrupted = Response(interrupted=True)
        with self.assertRaises(OSError):
            probe.page_snapshot(interrupted)
        self.assertTrue(interrupted.closed)



    def test_redirect_or_foreign_origin_cannot_certify_chat_page_or_assets(self):
        class Response:
            status = 200
            def __init__(self, url):
                self.url, self.closed = url, False
            def read(self, size):
                return b'<html>login</html>'
            def close(self):
                self.closed = True

        with patch.object(probe, 'BASE', 'http://127.0.0.1:8080'):
            route = '/nox-web-v29/pc/resonance.html'
            for url, reason in (
                ('http://127.0.0.1:8080/chat/login', 'HOLD_CHAT_RESPONSE_REDIRECT'),
                ('http://other.example/nox-web-v29/pc/resonance.html', 'HOLD_CHAT_RESPONSE_ORIGIN'),
                ('https://127.0.0.1:8080/nox-web-v29/pc/resonance.html', 'HOLD_CHAT_RESPONSE_ORIGIN'),
            ):
                response = Response(url)
                with self.subTest(url=url):
                    with self.assertRaisesRegex(RuntimeError, '^' + reason + '$'):
                        probe.page_snapshot(response, expected_path=route)
                self.assertTrue(response.closed)
            valid = Response('http://127.0.0.1:8080/nox-web-v29/pc/resonance.html?v=1')
            self.assertEqual(probe.page_snapshot(valid, expected_path=route)[1], route)
            self.assertTrue(valid.closed)
            for url, reason in (
                ('http://127.0.0.1:8080/chat/login', 'HOLD_CHAT_RESPONSE_REDIRECT'),
                ('https://external.example/app.js', 'HOLD_CHAT_RESPONSE_ORIGIN'),
            ):
                with self.subTest(asset=url), self.assertRaisesRegex(RuntimeError, '^' + reason + '$'):
                    probe.require_same_origin_target(Response(url), '/nox-web-v29/app.js')
        source = path.read_text()
        self.assertIn("page_snapshot(request(client,path), expected_path=path if path != '/' else None)", source)
        self.assertIn('require_exact_asset_target(asset,asset_request)', source)


    def test_same_path_html_login_fallback_never_certifies_resonance_asset(self):
        class AssetResponse:
            def __init__(self, mime):
                self.headers = {'Content-Type': mime}

        for mime, body in (
            ('text/html; charset=utf-8', b'console.log("not actually JS")'),
            ('application/xhtml+xml', b'<script>fake</script>'),
            ('application/javascript', b'\xef\xbb\xbf  <!DOCTYPE html><html>login</html>'),
            ('text/css', b'  <html><body>login</body></html>'),
            ('', b'<head><title>login</title></head>'),
        ):
            with self.subTest(mime=mime, body=body):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_RESONANCE_ASSET_HTML_FALLBACK$'):
                    probe.require_not_html_asset(AssetResponse(mime), body)
        for mime, body in (
            ('application/javascript', b'console.log("ready");'),
            ('text/css; charset=utf-8', b'body { color: inherit; }'),
            ('', b'export const ready = true;'),
        ):
            with self.subTest(mime=mime):
                self.assertIsNone(probe.require_not_html_asset(AssetResponse(mime), body))
        source = path.read_text()
        self.assertIn('require_not_html_asset(asset, sample)', source)
        self.assertIn('sample = asset.read(512)', source)
        self.assertIn("local.lower().endswith(('.js', '.mjs', '.css'))", source)

    def test_resonance_asset_mime_rejects_successful_json_error_bodies(self):
        class Response:
            def __init__(self, content_type):
                self.headers = {'Content-Type': content_type}

        for asset, content_type in (
            ('/nox-web-v29/app.js', 'application/javascript; charset=utf-8'),
            ('/nox-web-v29/app.mjs?v=2', 'text/javascript'),
            ('/nox-web-v29/theme.css', 'text/css; charset=UTF-8'),
        ):
            with self.subTest(ok=(asset, content_type)):
                self.assertIsNone(probe.require_browser_asset_mime(Response(content_type), asset))
        for asset, content_type in (
            ('/nox-web-v29/app.js', 'application/json'),
            ('/nox-web-v29/app.mjs', 'text/plain'),
            ('/nox-web-v29/theme.css', 'application/javascript'),
            ('/nox-web-v29/theme.css', ''),
            ('/nox-web-v29/app.js', 'text/html'),
            ('/nox-web-v29/app.js', 'application/json; charset=utf-8'),
        ):
            with self.subTest(hold=(asset, content_type)):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_RESONANCE_ASSET_MIME$'):
                    probe.require_browser_asset_mime(Response(content_type), asset)
        source = path.read_text()
        self.assertIn('require_browser_asset_mime(asset, local)', source)

    def test_resonance_versioned_asset_query_is_preserved_and_pinned(self):
        class Response:
            def __init__(self, url):
                self.url = url

        with patch.object(probe, 'BASE', 'http://127.0.0.1:8080'):
            local = '/nox-web-v29/pc/resonance.js'
            requested = local + '?v=29.3&lang=es'
            self.assertIsNone(probe.require_exact_asset_target(
                Response('http://127.0.0.1:8080' + requested), requested))
            for wrong_url, hold in (
                ('http://127.0.0.1:8080' + local, 'HOLD_RESONANCE_ASSET_QUERY_MISMATCH'),
                ('http://127.0.0.1:8080' + local + '?v=old&lang=es',
                 'HOLD_RESONANCE_ASSET_QUERY_MISMATCH'),
                ('http://127.0.0.1:8080/chat/login?v=29.3&lang=es',
                 'HOLD_CHAT_RESPONSE_REDIRECT'),
                ('https://127.0.0.1:8080' + requested, 'HOLD_CHAT_RESPONSE_ORIGIN'),
            ):
                with self.subTest(wrong_url=wrong_url):
                    with self.assertRaisesRegex(RuntimeError, '^' + hold + '$'):
                        probe.require_exact_asset_target(Response(wrong_url), requested)
        source = path.read_text()
        self.assertIn("asset_request=local + ('?' + target_parts.query if target_parts.query else '')", source)
        self.assertIn('with request(client,asset_request) as asset:', source)
        self.assertIn('require_exact_asset_target(asset,asset_request)', source)

    def test_obj_releases_http_response_on_success_and_hold(self):
        class Response:
            def __init__(self, status, payload, read_error=False):
                self.status, self.payload, self.closed = status, payload, False
                self.read_error = read_error
            def read(self, limit):
                if self.read_error:
                    raise OSError('synthetic-read-error')
                return self.payload[:limit]
            def close(self):
                self.closed = True

        ok = Response(200, b'{"ok":true}')
        self.assertEqual(probe.obj(ok), {'ok': True})
        self.assertTrue(ok.closed)
        for response, expected in (
            (Response(503, b'{}'), 'HOLD_HTTP_503'),
            (Response(200, b'x' * 11), 'HOLD_RESPONSE_LIMIT'),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(RuntimeError, expected):
                    probe.obj(response, limit=10)
                self.assertTrue(response.closed)
        malformed = Response(200, b'{')
        with self.assertRaises(ValueError):
            probe.obj(malformed)
        self.assertTrue(malformed.closed)
        interrupted = Response(200, b'{}', read_error=True)
        with self.assertRaises(OSError):
            probe.obj(interrupted)
        self.assertTrue(interrupted.closed)

    def test_owner_rest_json_readback_strict_evidence_and_socket_close(self):
        class Response:
            status = 200
            def __init__(self, payload):
                self.payload = payload
                self.closed = False
            def read(self, limit):
                return self.payload[:limit]
            def close(self):
                self.closed = True

        invalid = (
            (b'{"native_p02_bound":false,"native_p02_bound":true}',
             'HOLD_OWNER_JSON_DUPLICATE_KEY'),
            (b'{"workers":[{"id":"a","id":"b"}]}',
             'HOLD_OWNER_JSON_DUPLICATE_KEY'),
            (b'{"configured":NaN}', 'HOLD_OWNER_JSON_NONFINITE'),
            (b'{"events":[{"delay":Infinity}]}', 'HOLD_OWNER_JSON_NONFINITE'),
            (b'{"value":-Infinity}', 'HOLD_OWNER_JSON_NONFINITE'),
            (b'{"stats":{"overflow":1e999}}', 'HOLD_OWNER_JSON_NONFINITE'),
            (b'{"stats":[-1e999]}', 'HOLD_OWNER_JSON_NONFINITE'),
        )
        for payload, hold in invalid:
            with self.subTest(payload=payload):
                response = Response(payload)
                with self.assertRaisesRegex(RuntimeError, '^' + hold + '$'):
                    probe.obj(response)
                self.assertTrue(response.closed)
        good = Response(b'{"native_p02_bound":true,"workers":[{"id":"a"}],"delay":1.5,"rate":2.5e2}')
        self.assertEqual(probe.obj(good),
                         {'native_p02_bound': True, 'workers': [{'id': 'a'}], 'delay': 1.5, 'rate': 250.0})
        self.assertTrue(good.closed)

    def test_placeholders_and_invisible_unicode_do_not_count_as_visible_output(self):
        for text in ('', ' ', '\n', '...', '…\n', '. … .', '\u200b', '\u200d',
                     '\u2060', '\ufe0f', '\u034f', '\x00', '\u2028',
                     '.\u200b… \u200d\ufe0f', '\u200b\u2060'):
            with self.subTest(text=repr(text)):
                self.assertFalse(probe.meaningful_delta(text))
        for text in ('323', '0', 'Привет', 'hola', '😃', '¿', '\u200bОК'):
            with self.subTest(text=repr(text)):
                self.assertTrue(probe.meaningful_delta(text))

    def test_raw_nonnumeric_model_memory_is_never_exported(self):
        self.assertEqual(probe.numeric_public_answer(' **323**\n'), '323')
        self.assertEqual(probe.numeric_public_answer('323. Потом секрет: token=private'), '[NONNUMERIC_RESPONSE_WITHHELD]')
        self.assertEqual(probe.numeric_public_answer('12345678901234567890'), '[NONNUMERIC_RESPONSE_WITHHELD]')

    def test_first_meaningful_delta_is_measured_after_placeholder(self):
        clock = [0.0]
        class Response(SyntheticBoundedReader):
            status = 200
            closed = False
            def close(self): self.closed = True
            def __iter__(self):
                for at, frame in [(0.05, {'type':'preparing'}), (0.1, {'type':'start'}),
                                  (0.2, {'type':'delta','text':'…\n'}),
                                  (3.2, {'type':'delta','text':'323'}),
                                  (3.3, {'type':'done','dialog_id':'1'*32,'saved':True,'s03_integrated':True})]:
                    clock[0] = at
                    yield json.dumps(frame).encode()+b'\n'
        response = Response()
        with patch.object(probe, 'request', return_value=response), patch.object(probe.time, 'monotonic', side_effect=lambda:clock[0]):
            result = probe.consume_turn(object(), 'synthetic', '1'*32)
        self.assertEqual(result['first_meaningful_delta_ms'], 3200)
        self.assertEqual(result['placeholder_delta_count'], 1)
        self.assertEqual(result['stream_total_ms'], 3300)
        self.assertEqual([event['type'] for event in result['events']], ['preparing','start','delta','done'])
        self.assertTrue(response.closed)

    def test_full_two_turn_durable_history_and_fail_closed_completion(self):
        first, answer, second = '17 * 19?', '323', 'What number?'
        expected = [(first, answer), (second, answer)]
        messages = [{'role': 'user', 'content': first}, {'role': 'assistant', 'content': answer},
                    {'role': 'user', 'content': second}, {'role': 'assistant', 'content': answer}]
        self.assertTrue(probe.history_matches_turns(messages, expected))
        for corrupted in (
            [{'content': 'foreign session'}, *messages[1:]],
            messages[2:],
            [messages[0], messages[1], messages[3], messages[2]],
            [dict(messages[0], role='assistant'), *messages[1:]],
            [*messages[:3], dict(messages[3], role='user')],
            [{'content': first}, *messages[1:]],
            {'messages': messages},
            messages[:3],
        ):
            self.assertFalse(probe.history_matches_turns(corrupted, expected))
        self.assertIsNone(probe.require_durable_result(True, True, 'SECOND_TURN'))
        for saved, correct in ((False, True), (True, False), (False, False)):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_SECOND_TURN_NOT_ACCEPTED'):
                probe.require_durable_result(saved, correct, 'SECOND_TURN')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_FIRST_TURN_NOT_ACCEPTED'):
            probe.require_durable_result(False, True, 'FIRST_TURN')

    def test_executor_third_turn_requires_three_durable_pairs_and_owner_truth(self):
        turns = [('first', '323'), ('second', '323'), ('executor?', '6 executors + NOX')]
        rows = [{'role': role, 'content': content} for role, content in (
            ('user', 'first'), ('assistant', '323'), ('user', 'second'),
            ('assistant', '323'), ('user', 'executor?'), ('assistant', '6 executors + NOX'))]
        done = {'saved': True, 's03_integrated': True}
        self.assertIsNone(probe.require_executor_witness(done, rows, turns, True, True))
        failures = [
            (dict(done, saved=False), rows, True, True),
            (dict(done, s03_integrated=False), rows, True, True),
            (done, rows[2:], True, True),
            (done, [*rows[:4], dict(rows[4], role='assistant'), rows[5]], True, True),
            (done, [dict(rows[0], content='foreign'), *rows[1:]], True, True),
            (done, rows, False, True),
            (done, rows, True, False),
        ]
        for receipt, history, owner_ok, answer_ok in failures:
            with self.subTest(receipt=receipt, owner=owner_ok, answer=answer_ok, history=len(history)):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_EXECUTOR_TURN_NOT_ACCEPTED'):
                    probe.require_executor_witness(receipt, history, turns, owner_ok, answer_ok)

    def test_multiturn_required_before_new_dialog_post(self):
        for setting in (None, '', '0', 'true', 'yes'):
            with self.subTest(setting=setting):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_PROBE_MULTITURN_NOT_REQUESTED$'):
                    probe.require_multiturn_requested(setting)
        self.assertIsNone(probe.require_multiturn_requested('1'))
        source = path.read_text()
        self.assertLess(source.index("require_multiturn_requested(os.environ.get('NOX_PROBE_SECOND_TURN'))"),
                        source.index("'/api/ui/memory/dialogs/create'"))

    def test_skipped_executor_turn_is_not_success(self):
        self.assertIsNone(probe.require_executor_turn_budget(0))
        self.assertIsNone(probe.require_executor_turn_budget(209.999))
        for elapsed in (210, 210.001, 999):
            with self.subTest(elapsed=elapsed):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_EXECUTOR_TURN_BUDGET_EXHAUSTED'):
                    probe.require_executor_turn_budget(elapsed)
        # Both before issuing a third POST and after verifying its persistence,
        # the same wall-clock budget must be enforced before any COMPLETE.
        source = path.read_text()
        gate = 'require_executor_turn_budget(time.monotonic()-probe_started)'
        self.assertEqual(source.count(gate), 3)
        first_gate = source.index(gate)
        second_gate = source.index(gate, first_gate + 1)
        final_gate = source.rindex(gate)
        self.assertLess(first_gate, source.index('turn3=admitted_consume_turn('))
        self.assertLess(source.index('require_executor_witness(end,third_history,'), second_gate)
        self.assertLess(second_gate, source.index("emit('chat_recent_timing_after'"))
        self.assertGreater(final_gate, source.index("request(client,'/chat/logout'"))
        self.assertLess(final_gate, source.index("print('NOX_MAINT_REPAIR_COMPLETE=true'"))

    def test_scoped_history_requires_explicit_top_level_dialog_id(self):
        did = '1' * 32
        rows = [{'role': 'user', 'content': 'question'},
                {'role': 'assistant', 'content': '323'}]
        turns = [('question', '323')]
        self.assertTrue(probe.scoped_history_matches_turns(
            {'dialog_id': did, 'messages': rows}, turns, did))
        for invalid in ({'messages': rows},
                        {'dialog_id': None, 'messages': rows},
                        {'dialog_id': '', 'messages': rows},
                        {'dialog_id': '2' * 32, 'messages': rows},
                        rows):
            with self.subTest(invalid=invalid):
                self.assertFalse(probe.scoped_history_matches_turns(invalid, turns, did))
        self.assertFalse(probe.scoped_history_matches_turns(
            {'dialog_id': did, 'messages': rows[:1]}, turns, did))

    def test_stream_terminal_done_must_bind_to_requested_dialog(self):
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, rows): self.rows = rows; self.closed = False
            def close(self): self.closed = True
            def __iter__(self):
                return iter(json.dumps(row).encode()+b'\n' for row in self.rows)
        for terminal_id in (None, '2'*32):
            response = Response([{'type':'delta','text':'323'},
                                 {'type':'done','dialog_id':terminal_id,'saved':True,'s03_integrated':True}])
            with self.subTest(terminal_id=terminal_id), patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_STREAM_TERMINAL_DIALOG_MISMATCH'):
                    probe.consume_turn(object(), 'synthetic', '1'*32)
            self.assertTrue(response.closed)
        response = Response([{'type':'delta','text':'323'},
                             {'type':'done','dialog_id':'1'*32,'saved':True,'s03_integrated':True}])
        with patch.object(probe, 'request', return_value=response):
            result = probe.consume_turn(object(), 'synthetic', '1'*32)
        self.assertEqual(result['done']['dialog_id'], '1'*32)
        self.assertTrue(response.closed)

    def test_oversize_final_delta_is_rejected_before_done(self):
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, amount): self.amount = amount; self.closed = False
            def close(self): self.closed = True
            def __iter__(self):
                rows = ({'type':'delta','text':'x' * self.amount},
                        {'type':'done','dialog_id':'1'*32,'saved':True,'s03_integrated':True})
                return iter(json.dumps(row).encode()+b'\n' for row in rows)
        invalid = Response(10001)
        with patch.object(probe, 'request', return_value=invalid):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_STREAM_TEXT_LIMIT'):
                probe.consume_turn(object(), 'synthetic', '1'*32)
        self.assertTrue(invalid.closed)
        boundary = Response(10000)
        with patch.object(probe, 'request', return_value=boundary):
            result = probe.consume_turn(object(), 'synthetic', '1'*32)
        self.assertEqual(len(result['answer']), 10000)
        self.assertTrue(boundary.closed)

    def test_slots_read_only_current_model_port_and_fail_closed_schema(self):
        class SlotsResponse:
            def __init__(self, rows, status=200):
                self.status, self.rows, self.closed = status, rows, False
            def __enter__(self): return self
            def close(self): self.closed = True
            def __exit__(self, *unused): self.close()
            def read(self, limit): return json.dumps(self.rows).encode()
        good = SlotsResponse([{'is_processing': False}, {'processing': True}])
        with patch.object(probe, 'request', return_value=good) as http:
            self.assertEqual(probe.model_slots_state(object()), {'count': 2, 'busy': 1})
        self.assertEqual(http.call_args.args[1], '/slots')
        self.assertEqual(http.call_args.kwargs['base'], 'http://127.0.0.1:8098')
        self.assertTrue(good.closed)
        both = SlotsResponse([{'is_processing': False, 'processing': False},
                              {'is_processing': True, 'processing': True}])
        with patch.object(probe, 'request', return_value=both):
            self.assertEqual(probe.model_slots_state(object()), {'count': 2, 'busy': 1})
        self.assertTrue(both.closed)
        for invalid in ([], {}, [{'id': 1}], [{'is_processing': 0}],
                        [{'is_processing': 'false'}], [None],
                        [{'is_processing': False, 'processing': True}],
                        [{'is_processing': True, 'processing': False}],
                        [{'is_processing': False, 'processing': 0}]):
            with self.subTest(invalid=invalid), patch.object(
                    probe, 'request', return_value=SlotsResponse(invalid)):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_SLOTS_STATE_UNVERIFIED$'):
                    probe.model_slots_state(object())
        with patch.object(probe, 'request', side_effect=OSError('connection refused')):
            with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_SLOTS_ENDPOINT_UNAVAILABLE$'):
                probe.model_slots_state(object())
        with patch.object(probe, 'request', return_value=SlotsResponse([], status=404)):
            with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_SLOTS_ENDPOINT_UNAVAILABLE$'):
                probe.model_slots_state(object())


    def test_real_latency_targets_gate_completion_for_first_and_second_turn(self):
        good_first = {'first_meaningful_delta_ms': 8000, 'stream_total_ms': 25000}
        good_second = {'first_meaningful_delta_ms': 5000, 'stream_total_ms': 25000}
        self.assertIsNone(probe.require_latency_target(good_first, 'FIRST_TURN', 8000))
        self.assertIsNone(probe.require_latency_target(good_second, 'SECOND_TURN', 5000))
        for bad in (
            {'first_meaningful_delta_ms': 8001, 'stream_total_ms': 25000},
            {'first_meaningful_delta_ms': 5000, 'stream_total_ms': 25001},
            {'first_meaningful_delta_ms': 5001, 'stream_total_ms': 5000},
            {'first_meaningful_delta_ms': -1, 'stream_total_ms': 100},
            {'first_meaningful_delta_ms': float('nan'), 'stream_total_ms': 100},
            {'first_meaningful_delta_ms': True, 'stream_total_ms': 100},
            {'stream_total_ms': 100},
            {},
            None,
        ):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_PROBE_FIRST_TURN_LATENCY_TARGET$'):
                    probe.require_latency_target(bad, 'FIRST_TURN', 8000)
        with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_PROBE_SECOND_TURN_LATENCY_TARGET$'):
            probe.require_latency_target(
                {'first_meaningful_delta_ms': 5001, 'stream_total_ms': 10000},
                'SECOND_TURN', 5000)
        source = path.read_text()
        self.assertIn("require_latency_target(turn, 'FIRST_TURN', 8000)", source)
        self.assertIn("require_latency_target(follow, 'SECOND_TURN', 5000)", source)
        self.assertLess(source.index("require_durable_result(saved, numeric_public_answer(answer)=='323'"),
                        source.index("require_latency_target(turn, 'FIRST_TURN', 8000)"))
        self.assertLess(source.index("require_durable_result(passed, numeric_public_answer(answer2)=='323'"),
                        source.index("require_latency_target(follow, 'SECOND_TURN', 5000)"))

    def test_nonfinite_ndjson_metadata_must_hold_before_stream_success(self):
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, frames):
                self.frames, self.closed = frames, False
            def __iter__(self):
                return iter(frame + b'\n' for frame in self.frames)
            def close(self):
                self.closed = True

        did = '1' * 32
        valid_delta = b'{"type":"delta","text":"323"}'
        valid_done = ('{"type":"done","dialog_id":"' + did +
                      '","saved":true,"s03_integrated":true}').encode()
        invalid_streams = [
            [b'{"type":"delta","text":"323","meta":{"ratio":NaN}}', valid_done],
            [valid_delta, ('{"type":"done","dialog_id":"' + did +
                           '","saved":true,"s03_integrated":true,"meta":[Infinity]}').encode()],
            [b'{"type":"status","metadata":{"bad":-Infinity}}', valid_delta, valid_done],
            [b'{"type":"status","metadata":{"bad":1e999}}', valid_delta, valid_done],
            [b'{"type":"status","metadata":[-1e999]}', valid_delta, valid_done],
        ]
        for frames in invalid_streams:
            response = Response(frames)
            with self.subTest(frame=frames[0]), patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_STREAM_NONFINITE_JSON$'):
                    probe.consume_turn(object(), 'synthetic', did)
            self.assertTrue(response.closed)
        valid = Response([b'{"type":"status","meta":{"ratio":3.5,"finite":2.5e2}}', valid_delta, valid_done])
        with patch.object(probe, 'request', return_value=valid):
            self.assertEqual(probe.consume_turn(object(), 'synthetic', did)['answer'], '323')
        self.assertTrue(valid.closed)


    def test_duplicate_json_keys_in_any_stream_object_hold_before_terminal_acceptance(self):
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, frames):
                self.frames, self.closed = frames, False
            def __iter__(self):
                return iter(self.frames)
            def close(self):
                self.closed = True

        did = '1' * 32
        delta = b'{"type":"delta","text":"323"}\n'
        done = ('{"type":"done","dialog_id":"' + did +
                '","saved":true,"s03_integrated":true}\n').encode()
        ambiguous = (
            [b'{"type":"delta","type":"status","text":"323"}\n', done],
            [delta, ('{"type":"done","dialog_id":"' + did +
                     '","dialog_id":"' + did +
                     '","saved":true,"s03_integrated":true}\n').encode()],
            [delta, ('{"type":"done","dialog_id":"' + did +
                     '","saved":false,"saved":true,"s03_integrated":true}\n').encode()],
            [b'{"type":"meta","payload":{"count":1,"count":2}}\n', delta, done],
        )
        for index, frames in enumerate(ambiguous):
            response = Response(frames)
            with self.subTest(index=index), patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_STREAM_DUPLICATE_JSON_KEY$'):
                    probe.consume_turn(object(), 'synthetic', did)
            self.assertTrue(response.closed)
        valid = Response([b'{"type":"meta","payload":{"count":2}}\n', delta, done])
        with patch.object(probe, 'request', return_value=valid):
            self.assertEqual(probe.consume_turn(object(), 'synthetic', did)['answer'], '323')
        self.assertTrue(valid.closed)


    def test_stream_terminal_requires_clean_eof_and_single_done(self):
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, frames):
                self.frames, self.closed = frames, False
            def __iter__(self):
                return iter(self.frames)
            def close(self):
                self.closed = True

        did = '1' * 32
        delta = b'{"type":"delta","text":"323"}\n'
        done = ('{"type":"done","dialog_id":"' + did +
                '","saved":true,"s03_integrated":true}\n').encode()
        cases = (
            ([delta, done], None),
            ([delta, done, b'{"type":"delta","text":"late"}\n'], 'HOLD_STREAM_TRAILING_AFTER_DONE'),
            ([delta, done, done], 'HOLD_STREAM_TRAILING_AFTER_DONE'),
            ([delta, done, b'{"type":"error"}\n'], 'HOLD_STREAM_TRAILING_AFTER_DONE'),
            ([delta, done, b'\n'], 'HOLD_STREAM_TRAILING_AFTER_DONE'),
            ([delta, done[:-1]], 'HOLD_STREAM_MISSING_NEWLINE'),
            ([delta[:-1], done], 'HOLD_STREAM_MISSING_NEWLINE'),
        )
        for frames, expected in cases:
            response = Response(frames)
            with self.subTest(expected=expected, length=len(frames)), patch.object(
                    probe, 'request', return_value=response):
                if expected is None:
                    self.assertEqual(probe.consume_turn(object(), 'synthetic', did)['answer'], '323')
                else:
                    with self.assertRaisesRegex(RuntimeError, '^' + expected + '$'):
                        probe.consume_turn(object(), 'synthetic', did)
            self.assertTrue(response.closed)


    def test_truncated_or_error_stream_cannot_pass(self):
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, rows): self.rows = rows; self.closed = False
            def close(self): self.closed = True
            def __iter__(self):
                return iter(json.dumps(row).encode()+b'\n' for row in self.rows)
        for rows, code in [([{'type':'delta','text':'323'}], 'INCOMPLETE_OR_PLACEHOLDER'),
                           ([{'type':'delta','text':'…'}, {'type':'done','dialog_id':'1'*32}], 'INCOMPLETE_OR_PLACEHOLDER'),
                           ([{'type':'error','error':'PRIVATE_PROVIDER_TEXT'}], 'HOLD_STREAM_ERROR')]:
            response = Response(rows)
            with patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, code):
                    probe.consume_turn(object(), 'synthetic', '1'*32)
            self.assertTrue(response.closed)


    def test_scoped_history_rejects_foreign_dialog_even_with_identical_turns(self):
        did, other = '1' * 32, '2' * 32
        turns = [('first', '323'), ('second', '323'), ('third', 'six')]
        messages = [{'role': role, 'content': content} for role, content in (
            ('user', 'first'), ('assistant', '323'), ('user', 'second'),
            ('assistant', '323'), ('user', 'third'), ('assistant', 'six'))]
        good = {'dialog_id': did, 'messages': messages}
        self.assertTrue(probe.scoped_history_matches_turns(good, turns, did))
        self.assertFalse(probe.scoped_history_matches_turns({'messages': messages}, turns, did))
        tagged = [dict(row, dialog_id=did) for row in messages]
        self.assertTrue(probe.scoped_history_matches_turns({'dialog_id': did, 'messages': tagged}, turns, did))
        corrupted = [
            {'dialog_id': other, 'messages': messages},
            {'dialog_id': None, 'messages': messages},
            {'dialog_id': did, 'messages': [dict(messages[0], dialog_id=other), *messages[1:]]},
            {'dialog_id': did, 'messages': [*messages[:-1], dict(messages[-1], dialog_id=other)]},
            {'dialog_id': did, 'messages': [*messages[:-1], dict(messages[-1], dialog_id=None)]},
            {'dialog_id': did, 'messages': tagged[2:]},
        ]
        for history in corrupted:
            with self.subTest(history=history):
                self.assertFalse(probe.scoped_history_matches_turns(history, turns, did))
                with self.assertRaisesRegex(RuntimeError, '^HOLD_CHAT_PROBE_EXECUTOR_TURN_NOT_ACCEPTED$'):
                    probe.require_executor_witness(
                        {'saved': True, 's03_integrated': True}, history, turns, True, True, did)
        self.assertIsNone(probe.require_executor_witness(
            {'saved': True, 's03_integrated': True}, good, turns, True, True, did))


    def test_done_frame_with_error_or_failed_status_cannot_certify_stream(self):
        """Saved=true must not hide an upstream error inside the done frame."""
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, terminal):
                self.terminal, self.closed = terminal, False
            def __iter__(self):
                frames = [
                    {'type': 'delta', 'text': '323'},
                    dict({'type': 'done', 'dialog_id': '1' * 32,
                          'saved': True, 's03_integrated': True}, **self.terminal),
                ]
                return iter(json.dumps(row).encode() + b'\n' for row in frames)
            def close(self):
                self.closed = True

        failed = [
            {'error': 'upstream timeout'},
            {'error': {'code': 'provider_failure'}},
            {'status': 'error'},
            {'status': 'failed'},
            {'status': 'cancelled'},
            {'status': 'aborted'},
            {'success': False},
        ]
        for flags in failed:
            response = Response(flags)
            with self.subTest(flags=flags), patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_STREAM_TERMINAL_FAILURE$'):
                    probe.consume_turn(object(), 'synthetic', '1' * 32)
            self.assertTrue(response.closed)

        accepted = Response({'error': None, 'status': 'completed', 'success': True})
        with patch.object(probe, 'request', return_value=accepted):
            result = probe.consume_turn(object(), 'synthetic', '1' * 32)
        self.assertEqual(result['answer'], '323')
        self.assertTrue(accepted.closed)

def test_preterminal_failure_cannot_be_laundered_by_saved_done(self):
        """A failed status/meta/delta must poison a later success terminal."""
        did = '1' * 32
        class Response(SyntheticBoundedReader):
            status = 200
            def __init__(self, frames):
                self.frames, self.closed = frames, False
            def __iter__(self):
                return iter(json.dumps(row).encode() + b'\n' for row in self.frames)
            def close(self):
                self.closed = True

        done = {'type': 'done', 'dialog_id': did,
                'saved': True, 's03_integrated': True}
        bad = (
            {'type': 'status', 'status': 'failed'},
            {'type': 'status', 'status': ' ABORTED '},
            {'type': 'meta', 'error': {'code': 'provider_failure'}},
            {'type': 'started', 'success': False},
            {'type': 'delta', 'text': '323', 'error': 'timeout'},
        )
        for frame in bad:
            response = Response([frame, {'type': 'delta', 'text': '323'}, done])
            with self.subTest(frame=frame), patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, '^HOLD_STREAM_PRETERMINAL_FAILURE$'):
                    probe.consume_turn(object(), 'synthetic', did)
            self.assertTrue(response.closed)
        healthy = Response([{'type': 'status', 'status': 'running', 'success': True},
                            {'type': 'delta', 'text': '323'}, done])
        with patch.object(probe, 'request', return_value=healthy):
            self.assertEqual(probe.consume_turn(object(), 'synthetic', did)['answer'], '323')
        self.assertTrue(healthy.closed)


if __name__ == '__main__':
    unittest.main()
