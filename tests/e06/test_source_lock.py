"""E06 original application SourceLock contracts: synthetic malicious archives, no model downloads."""
import io
import json
import unittest
import zipfile
from pathlib import Path
from coordination.e06.canonical_source_lock import (
    EXPECTED_ARCHIVE, EXPECTED_FILES, HOST_FILES, analyze_zip, attest_routes,
    canonical_tree, safe_member, verify_json_assets, NO_RELEASE,
)

def zip_of(mapping):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for path, data in mapping.items():
            z.writestr(path, data)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)

class CanonicalSourceLockTests(unittest.TestCase):
    def test_01_exact_original_archive_and_member_constants(self):
        self.assertEqual(len(EXPECTED_ARCHIVE), 64)
        self.assertEqual(EXPECTED_FILES, 729)
        self.assertEqual(NO_RELEASE, "ORIGINAL_BASELINE_ONLY_NOT_INTEGRATED")

    def test_02_zip_member_traversal_denied(self):
        for path in ("../a", "dir/../x", "/absolute", "C:x", "dir//foo"):
            with self.subTest(path=path):
                with zip_of({path: "data"}) as z:
                    with self.assertRaises(ValueError):
                        safe_member(z.infolist()[0])

    def test_03_zip_windows_devices_and_colons_denied(self):
        for path in ("CON", "A/NUL.json", "COM1.txt", "folder/a:b", "folder/trailing. "):
            with self.subTest(path=path):
                with zip_of({path: "data"}) as z:
                    with self.assertRaises(ValueError):
                        analyze_zip(z, enforce_baseline=False)

    def test_04_windows_case_alias_rejected(self):
        with zip_of({"ABC.txt": "x", "abc.TXT": "y"}) as z:
            with self.assertRaisesRegex(ValueError, "ZIP_CASE_COLLISION"):
                analyze_zip(z, enforce_baseline=False)

    def test_05_member_sha_and_byte_counts_are_precise(self):
        with zip_of({"a.txt": "abc", "b.txt": "x"}) as z:
            rows, total = analyze_zip(z, enforce_baseline=False)
        self.assertEqual(total, 4)
        self.assertEqual(rows[0]["sha256"], "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_06_domain_separated_tree_has_stable_order(self):
        with zip_of({"b.txt": "b", "a.txt": "a"}) as z:
            first, _ = analyze_zip(z, enforce_baseline=False)
        self.assertEqual(canonical_tree(first), canonical_tree(list(reversed(first))))
        self.assertNotEqual(canonical_tree(first), canonical_tree(first[:1]))

    def test_07_manifest_invalid_fails_closed(self):
        with zip_of({"assets/personas_5.json": "not-json"}) as z:
            rows, _ = analyze_zip(z, enforce_baseline=False)
            d = verify_json_assets(z, rows)
        self.assertEqual(d["assets/personas_5.json"], "INVALID")

    def test_08_original_host_explicitly_python(self):
        self.assertEqual(len(HOST_FILES), 4)
        self.assertNotIn("MainWindow.xaml", HOST_FILES)

    def test_09_route_proposal_not_native_integration(self):
        m = {"schema": "NOX_PACK01_NATIVE_BINDING_MAP_V1", "counts": {"sourceOwnerMethodBound": 1},
             "routes": [{"routeId": f"route.{n}", "taskId": f"NIP01-{n:02d}", "owner": 2,
                         "exeIntegrated": False, "hardwareAccepted": False, "releaseAccepted": False,
                         "sourceBinding": "proposals/NOX-PACK01-50/native_bridge.py:Adapter.chat" if n == 1 else None}
                        for n in range(1, 51)]}
        result=attest_routes(m)
        self.assertEqual(result["source_method_candidates"], 1)
        self.assertEqual(result["canonical_host_bound"], 0)
        self.assertEqual(result["release_accepted"], 0)

    def test_10_route_forged_acceptance_and_count_denied(self):
        m = {"schema": "NOX_PACK01_NATIVE_BINDING_MAP_V1", "counts": {"sourceOwnerMethodBound": 0},
             "routes": [{"routeId": f"route.{n}", "taskId": f"NIP01-{n:02d}", "owner": 2,
                         "exeIntegrated": False, "hardwareAccepted": False, "releaseAccepted": False,
                         "sourceBinding": None} for n in range(1, 51)]}
        m["routes"][0]["exeIntegrated"] = True
        with self.assertRaises(ValueError):
            attest_routes(m)
        m["routes"][0]["exeIntegrated"] = False
        m["routes"][1]["routeId"] = m["routes"][0]["routeId"]
        with self.assertRaises(ValueError):
            attest_routes(m)

if __name__ == "__main__":
    unittest.main()
