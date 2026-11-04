"""Test live owner diagnostic function from exact repo source, no fake Windows PASS."""
import ast
import hashlib
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/t06_local_onehost_bridge.py"

def owner():
    text=SOURCE.read_text("utf-8")
    tree=ast.parse(text)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)
           and n.name=="installed_manifest_failure_evidence"]
    assert len(nodes)==1
    namespace={"hashlib":hashlib}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),"exec"),namespace)
    return namespace["installed_manifest_failure_evidence"],text

class OwnerManifestCIRegression(unittest.TestCase):
    def test_not_run(self):
        f,_=owner()
        self.assertEqual(f({})["status"],"NOT_RUN")
    def test_pass_does_not_claim_release(self):
        f,_=owner()
        self.assertFalse(f({"verify":{"code":0}})["release_accepted"])
    def test_unknown_installed_metadata_flag(self):
        f,_=owner()
        self.assertEqual(f({"verify":{"code":1,"stderr_tail":
            "A parameter cannot be found that matches parameter name 'AllowInstalledMetadata'."}})["reason"],
            "INSTALLED_METADATA_PARAMETER_UNSUPPORTED")
    def test_marker(self):
        f,_=owner()
        self.assertEqual(f({"verify":{"code":1,"stderr_tail":"P01_PAYLOAD_VERIFY_FAILED: invalid backup ownership marker"}})["reason"],
                         "INVALID_OWNER_MARKER")
    def test_duplicate_json(self):
        f,_=owner()
        self.assertEqual(f({"verify":{"code":1,"stderr_tail":"P01_PAYLOAD_VERIFY_FAILED: duplicate or invalid JSON manifest"}})["reason"],
                         "MANIFEST_JSON_AMBIGUOUS")
    def test_redacted_unknown(self):
        f,_=owner()
        receipt=f({"verify":{"code":1,"stderr_tail":"secret=MY-SECRET C:\\Users\\private\\"}})
        self.assertEqual(receipt["reason"],"UNKNOWN_VERIFY_ERROR")
        self.assertNotIn("MY-SECRET",str(receipt))
    def test_printed_before_generic_g4(self):
        _,s=owner()
        self.assertLess(s.index("T06_INSTALLED_MANIFEST_VERIFY_ROOT_EVIDENCE"),
                        s.index("NOX_EXPRESS_GATE_4_INSTALLED_RESULT"))
        self.assertIn('data["installed_manifest_verify"]=owner_manifest_evidence',s)

if __name__=="__main__":
    unittest.main()
