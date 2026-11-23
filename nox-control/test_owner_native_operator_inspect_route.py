"""Pin the exact read-only inspect entrypoint used by /nox-maintain."""
import ast
import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
EXPECTED_INSPECT = 'nox-control/owner_native_inspect.py'


def load(path):
    spec = importlib.util.spec_from_file_location('inspect_route_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OwnerInspectRouteTests(unittest.TestCase):
    def test_canonical_owner_action_selects_exact_cgroup_inspector_asset(self):
        operator_path = HERE / 'owner_native_operator.py'
        operator = load(operator_path)
        self.assertEqual(operator.FILES['inspect'], EXPECTED_INSPECT)
        self.assertNotEqual(
            operator.FILES['inspect'],
            'nox-control/systemic_relay_20261118/owner_systemic_relay_observe.py')

        source_path = HERE.parent / operator.FILES['inspect']
        self.assertTrue(source_path.is_file())
        self.assertFalse(source_path.is_symlink())
        inspector = source_path.read_text()
        self.assertIn('def cgroup_process_pin(', inspector)
        self.assertIn("result['cgroup_pin'] = cgroup_process_pin(", inspector)
        self.assertIn('process(int(m[3]), include_cgroup=True)', inspector)
        self.assertIn("emit('SNAPSHOT_A',runtime_snapshot())", inspector)
        self.assertIn("emit('SNAPSHOT_B',runtime_snapshot())", inspector)

    def test_inspect_uses_exact_entrypoint_without_bundle_rewrite(self):
        source = (HERE / 'owner_native_operator.py').read_text()
        tree = ast.parse(source)
        run_native = next(node for node in tree.body
                          if isinstance(node, ast.FunctionDef)
                          and node.name == 'run_native')
        direct_payload = [node for node in ast.walk(run_native)
                          if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name)
                                  and target.id == 'payload'
                                  for target in node.targets)
                          and ast.dump(node.value, include_attributes=False)
                          == ast.dump(ast.parse(
                              'Path(FILES[action]).read_text()',
                              mode='eval').body, include_attributes=False)]
        self.assertEqual(len(direct_payload), 1)

        bundle_branches = [node for node in run_native.body
                           if isinstance(node, ast.If)
                           and ast.get_source_segment(source, node.test)
                           and ('action' in ast.get_source_segment(source, node.test))]
        self.assertTrue(bundle_branches)
        self.assertTrue(all(
            'inspect' not in (ast.get_source_segment(source, node.test) or '')
            for node in bundle_branches))

    def test_exact_source_pin_is_still_bound_to_owner_command_and_checkout(self):
        source = (HERE / 'owner_native_operator.py').read_text()
        tree = ast.parse(source)
        authorize = next(node for node in tree.body
                         if isinstance(node, ast.FunctionDef)
                         and node.name == 'authorize_event')
        text = ast.get_source_segment(source, authorize)
        self.assertIn("'/nox-maintain {INSTANCE} {sha} {action}'", text)
        self.assertIn("git','rev-parse','HEAD", text)
        self.assertIn("raise RuntimeError('HOLD_CHECKOUT_MISMATCH')", text)


    def test_exact_lookup_owner_scope_and_fail_closed(self):
        from unittest import mock
        import io
        import urllib.error
        import sys
        sys.path.insert(0, str(HERE.parent))
        from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as probe
        opener = mock.Mock()
        with mock.patch.object(probe.urllib.request, 'build_opener', return_value=opener) as build:
            def answer(body):
                opener.open.side_effect = None
                opener.open.return_value = io.BytesIO(body)
            answer(b'{"instances":{"id":60509551,"actual_status":"stopped"}}')
            self.assertEqual(probe.exact_owner_instance('test-token')['actual_status'], 'stopped')
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, probe.API + '/instances/60509551/?owner=me')
            self.assertEqual(request.get_method(), 'GET')
            self.assertIsInstance(build.call_args.args[0], probe._ExactLookupNoRedirect)
            self.assertIsNone(build.call_args.args[0].redirect_request(None,None,302,None,None,'https://example.invalid'))
            for body, error in (
                (b'{"instances":[]}', 'HOLD_PROVIDER_RESPONSE_SHAPE'),
                (b'{"instances":{"id":1}}', 'HOLD_EXACT_INSTANCE_IDENTITY'),
                (b'{"success":false}', 'HOLD_PROVIDER_RESPONSE'),
                (b'not json', 'HOLD_PROVIDER_RESPONSE'),
            ):
                answer(body)
                with self.assertRaisesRegex(RuntimeError, error):
                    probe.exact_owner_instance('test-token')
            for status, error in ((404, 'HOLD_EXACT_INSTANCE_NOT_VISIBLE'),
                                  (403, 'HOLD_PROVIDER_HTTP_403')):
                opener.open.side_effect = urllib.error.HTTPError(
                    request.full_url, status, 'error', {}, io.BytesIO(b''))
                with self.assertRaisesRegex(RuntimeError, error):
                    probe.exact_owner_instance('test-token')
        operator = load(HERE / 'owner_native_operator.py')
        with mock.patch.dict(operator.os.environ, {'NOX2':'test-token'}):
            with mock.patch.object(probe, 'exact_owner_instance',
                                   return_value={'id':60509551,'actual_status':'stopped','num_gpus':2}):
                with mock.patch.object(probe, 'api') as api:
                    with self.assertRaisesRegex(RuntimeError, 'HOLD_EXACT_RUNNING_INSTANCE'):
                        operator.run_native('inspect', 1)
                    api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
