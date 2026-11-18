"""Source-only guard for the serving chat's WEB29 public asset and pin."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
FILES = (
    HERE / "owner_chat_decomposition_install.py",
    HERE / "package_v4/owner_chat_decomposition_entry.py",
    HERE / "package_v4/owner_chat_decomposition_embedded_entry.py",
)


def public_path(file):
    module = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    values = [
        assignment.value for assignment in module.body
        if isinstance(assignment, ast.Assign)
        and len(assignment.targets) == 1
        and isinstance(assignment.targets[0], ast.Name)
        and assignment.targets[0].id == "PUBLIC_ASSET_PATH"
    ]
    if len(values) != 1:
        raise AssertionError("HOLD_PUBLIC_ASSET_BINDING")
    return ast.literal_eval(values[0])


class RouteContractTests(unittest.TestCase):
    def test_route_matches_pinned_native_web_manifest(self):
        manifest = json.loads((HERE / "frontend_candidate_current.json").read_text())
        self.assertEqual(manifest["http_path"], "/nox-web-v29/pc/v24/nox-v24-chat.js")
        for source in FILES:
            with self.subTest(source=source.name):
                self.assertEqual(public_path(source), manifest["http_path"])

    def test_embedded_pins_match_exact_candidate_bytes(self):
        build = json.loads((HERE / "package_v4/embedded_build.json").read_text())
        for source, key in ((FILES[1], "template_sha256"),
                            (FILES[2], "entry_sha256")):
            with self.subTest(source=source.name):
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), build[key])


if __name__ == "__main__":
    unittest.main()
