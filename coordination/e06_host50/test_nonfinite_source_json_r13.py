"""E06 R13 source-only regression: reject non-standard JSON numeric constants."""
import json
import tempfile
import unittest
from pathlib import Path
from admission import (APPROVED_ROUTE_POLICY, BASE_COMMIT, Hold,
                       run_read_only_audit)

class StrictSourceJSONTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        root = Path(self.workspace.name)
        self.catalog_path = root / 'catalog.json'
        self.binding_path = root / 'binding.json'
        actions = [dict(taskId=f'NIP01-{i:02}', routeId=route,
                        owner=owner, risk=risk, settings=[])
                   for i, (route, owner, risk) in enumerate(APPROVED_ROUTE_POLICY, 1)]
        self.catalog = {'version':'NOX-INTEGRATION-PACK-01', 'actions':actions}
        self.bindings = {'sourceBaseCommit':BASE_COMMIT, 'routes':[
            dict(taskId=a['taskId'], routeId=a['routeId'], owner=a['owner'],
                 sourceBinding=None) for a in actions]}

    def _run_with_token(self, token):
        self.catalog_path.write_text(json.dumps(self.catalog), encoding='utf8')
        payload = json.dumps(self.bindings)[:-1] + ',"untrustedDiagnostic":' + token + '}'
        self.binding_path.write_text(payload, encoding='utf8')
        return run_read_only_audit(str(self.catalog_path), str(self.binding_path))

    def test_valid_json_keeps_full_50_route_audit(self):
        result = self._run_with_token('null')
        self.assertEqual(len(result['routes']), 50)
        self.assertEqual(result['sourceBound'], 0)

    def test_nonfinite_nan_rejected(self):
        with self.assertRaises(Hold):
            self._run_with_token('NaN')

    def test_nonfinite_positive_infinity_rejected(self):
        with self.assertRaises(Hold):
            self._run_with_token('Infinity')

    def test_nonfinite_negative_infinity_rejected(self):
        with self.assertRaises(Hold):
            self._run_with_token('-Infinity')

if __name__ == '__main__':
    unittest.main()
