"""NOX E06 host50 focused offline smoke checks. No Windows native operations."""
import unittest
from admission import BASE_COMMIT, BASE_TREE, Hold, Denied, audit_registry, validate_origin

class AdmissionSourceTests(unittest.TestCase):
    def test_exact_origin(self):
        self.assertEqual(validate_origin("https://nox.invalid"), "https://nox.invalid")
        with self.assertRaises(Denied):
            validate_origin("http://nox.invalid")
        with self.assertRaises(Denied):
            validate_origin("https://nox.invalid:4443")
    def test_duplicate_route_is_hold(self):
        names = ["route%02d" % i for i in range(1, 51)]
        owners = [2] * 50
        catalog = {"version": "NOX-INTEGRATION-PACK-01", "actions": [
            {"taskId": "NIP01-%02d" % i, "routeId": names[i-1], "owner": owners[i-1], "risk": "safe", "settings": []}
            for i in range(1, 51)]}
        bindings = {"sourceBaseCommit": BASE_COMMIT, "routes": [
            {"taskId": "NIP01-%02d" % i, "routeId": names[i-1], "owner": owners[i-1], "sourceBinding": None}
            for i in range(1, 51)]}
        self.assertEqual(audit_registry(catalog,bindings)["unbound"],50)
        bindings["routes"][1]["routeId"] = names[0]
        with self.assertRaises(Hold):
            audit_registry(catalog,bindings)
    def test_no_product_progress_in_source_map(self):
        self.assertEqual(len(BASE_COMMIT),40)
        self.assertEqual(len(BASE_TREE),40)

if __name__ == "__main__":
    unittest.main()
