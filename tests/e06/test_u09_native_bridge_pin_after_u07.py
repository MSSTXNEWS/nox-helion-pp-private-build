"""U09: the existing exact-source gate must pin the reviewed U07 offline bridge."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
STAGE=ROOT/"coordination/e06/stage_native_stdio.py"
BRIDGE=ROOT/"proposals/NOX-PACK01-50/native_bridge.py"
APPROVED_U07_BLOB="b03087d12b42bea409cdf1c69016c4fd510867d5"
PREVIOUS_BLOB="6acacc7396130f9ff536c2033601bfa09c9cce72"

def pinned_addons():
    module=ast.parse(STAGE.read_text(encoding="utf-8"))
    definitions=[node.value for node in module.body if isinstance(node,ast.Assign)
                 and any(isinstance(target,ast.Name) and target.id=="ADDONS"
                         for target in node.targets)]
    if len(definitions)!=1:
        raise AssertionError("E06 immutable addon list must be unique")
    return ast.literal_eval(definitions[0])

def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+b"\0"+data).hexdigest()

class U09PinnedNativeBridge(unittest.TestCase):
    def test_reviewed_original_p02_source_is_exact_u07_blob(self):
        matches=[row for row in pinned_addons() if row[:2]==(
            "proposals/NOX-PACK01-50/native_bridge.py","nox_native_bridge.py")]
        self.assertEqual(len(matches),1)
        source=BRIDGE.read_bytes()
        self.assertEqual(git_blob(source),APPROVED_U07_BLOB)
        self.assertEqual(matches[0][2],APPROVED_U07_BLOB)
        self.assertNotEqual(matches[0][2],PREVIOUS_BLOB)

    def test_pin_gate_is_not_removed_or_weakened(self):
        spec=importlib.util.spec_from_file_location("u09_original_e06_stage",STAGE)
        stage=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stage)
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"preimage.py"
            file.write_bytes(b"print('owner')\n")
            original=file.read_bytes()
            with self.assertRaisesRegex(RuntimeError,"E06_NATIVE_OWNER_BLOB_SHA_HOLD"):
                stage.pinned_bytes(file,APPROVED_U07_BLOB)
            self.assertEqual(file.read_bytes(),original)
            self.assertEqual(stage.pinned_bytes(file,git_blob(original)),original)

if __name__=="__main__":
    unittest.main()
