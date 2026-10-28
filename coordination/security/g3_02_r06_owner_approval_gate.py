"""E06 NOX V16 R06 / PR27 immutable source-only approval transaction gate.

Conservative HOLD on evidence of shared mutable payload. No Windows/native
acceptance claim; no executable system operation is performed.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest

SOURCE_BLOB = "486e4d29a2f4d859a2923122706657915da011aa"
CATALOG_BLOB = "c8c9b19e44d9b5ff3af00a38e8446d8c0507b69d"
DANGEROUS = {"training.start": 4, "calls.dial": 2, "system.update": 1,
             "system.backup": 1, "system.pc_control": 1}


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def check_source(text):
    tree = ast.parse(text)
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef)
                and n.name == "NoxPackHost"), None)
    if cls is None:
        return {"status": "HOLD_MISSING_CLASS"}
    fn = next((n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name == "execute"), None)
    if fn is None:
        return {"status": "HOLD_MISSING_EXECUTE"}
    calls = sorted((n for n in ast.walk(fn) if isinstance(n, ast.Call)),
                   key=lambda n: (n.lineno, n.col_offset))
    approvals = [n for n in calls if isinstance(n.func, ast.Attribute)
                 and n.func.attr == "native_approve"
                 and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == "self"]
    owners = [n for n in calls if isinstance(n.func, ast.Attribute)
              and n.func.attr == "call"
              and isinstance(n.func.value, ast.Name)
              and n.func.value.id == "port"]
    probes = [n for n in calls if isinstance(n.func, ast.Attribute)
              and n.func.attr == "available"
              and isinstance(n.func.value, ast.Name)
              and n.func.value.id == "port"]
    if len(approvals) != 1 or len(owners) != 1:
        return {"status": "HOLD_UNVERIFIED_CALL_SEQUENCE"}
    a, o = approvals[0], owners[0]
    same = (len(a.args) >= 3 and len(o.args) >= 2 and
            isinstance(a.args[2], ast.Name) and isinstance(o.args[1], ast.Name)
            and a.args[2].id == o.args[1].id == "payload")
    return {"status": "HOLD_SHARED_MUTABLE_PAYLOAD" if same else "REVIEW_REQUIRED",
            "approval_line": a.lineno, "owner_call_line": o.lineno,
            "probe_between": any(a.lineno < p.lineno < o.lineno for p in probes),
            "accepted": False}


def check_catalog(text):
    data = json.loads(text)
    actions = data.get("actions")
    if data.get("version") != "NOX-INTEGRATION-PACK-01" or not isinstance(actions, list) or len(actions) != 50:
        raise ValueError("catalog size/version mismatch")
    routes = {row["routeId"]: row for row in actions}
    if len(routes) != 50:
        raise ValueError("duplicate route")
    for name, owner in DANGEROUS.items():
        row = routes.get(name)
        if not row or row.get("risk") != "dangerous" or type(row.get("owner")) is not int or row["owner"] != owner:
            raise ValueError("dangerous route downgrade: " + name)
    return True


def audit(source_path, catalog_path):
    src = Path(source_path).read_bytes()
    cat = Path(catalog_path).read_bytes()
    if git_blob(src) != SOURCE_BLOB or git_blob(cat) != CATALOG_BLOB:
        return {"status": "HOLD_PREIMAGE_MISMATCH", "accepted": False}
    check_catalog(cat.decode("utf-8"))
    return check_source(src.decode("utf-8"))


class Tests(unittest.TestCase):
    def test_shared_payload_hold(self):
        s = "class NoxPackHost:\n def execute(self,route,payload,session):\n  self.native_approve(session,route,payload)\n  port.available()\n  return port.call(session,payload)\n"
        self.assertEqual(check_source(s)["status"], "HOLD_SHARED_MUTABLE_PAYLOAD")
        self.assertTrue(check_source(s)["probe_between"])

    def test_copy_never_means_accepted(self):
        s = "class NoxPackHost:\n def execute(self,route,payload,session):\n  self.native_approve(session,route,payload)\n  return port.call(session,copy_payload)\n"
        self.assertEqual(check_source(s)["status"], "REVIEW_REQUIRED")
        self.assertFalse(check_source(s)["accepted"])

    def test_missing_class_holds(self):
        self.assertEqual(check_source("x=1")["status"], "HOLD_MISSING_CLASS")

    def test_git_blob_known(self):
        self.assertEqual(git_blob(b"test"), "30d74d258442c7c65512eafab474568dd706c430")

    def test_unpinned_source_holds(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p, c = Path(d)/"native_bridge.py", Path(d)/"catalog.json"
            p.write_text("x=1"); c.write_text("{}")
            self.assertEqual(audit(p,c)["status"], "HOLD_PREIMAGE_MISMATCH")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--catalog")
    args = ap.parse_args()
    if args.source or args.catalog:
        if not args.source or not args.catalog:
            print("HOLD: source and catalog required", file=sys.stderr)
            sys.exit(2)
        try:
            result = audit(args.source, args.catalog)
        except (OSError, ValueError, SyntaxError) as exc:
            result = {"status": "HOLD_UNVERIFIED", "reason": str(exc)}
        print(json.dumps(result, sort_keys=True))
        sys.exit(2)  # Never turn static source inspection into Windows ACCEPTED.
    unittest.main()
