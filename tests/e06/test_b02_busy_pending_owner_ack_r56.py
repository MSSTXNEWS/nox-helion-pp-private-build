"""B02 R56: source-derived refusal-state fence for both original WPF consumers.

These checks analyze the exact checked-out C# classifiers. They do NOT compile
C#, execute installed IPC, or constitute an E06/E07 physical acceptance.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"
LEGACY = ROOT / "coordination/e06/MainWindow.NativeP02.cs"


def native_denial_classifier(path: Path, method: str, next_method: str):
    source = path.read_text(encoding="utf-8")
    head = "private static bool " + method
    assert source.count(head) == 1, f"ambiguous original owner method: {method}"
    segment = source.split(head, 1)[1].split(next_method, 1)[0]
    assert "ToUpperInvariant()" in segment
    assert "Regex.Replace(status.Trim()" in segment
    if method.startswith("NativeOwner"):
        condition = re.search(r'if\s*\(value is ([\s\S]*?)\)\s*return true;', segment)
        assert condition is not None
        exact = set(re.findall(r'"([A-Z_]+)"', condition.group(1)))
        suffixes = set(re.findall(r'EndsWith\("([A-Z_]+)"', segment))
        prefixes = set(re.findall(r'StartsWith\("([A-Z_]+)"', segment))
    else:
        blocks = segment.split("foreach (var exact in new[]", 1)
        assert len(blocks) == 2
        exact = set(re.findall(r'"([A-Z_]+)"', blocks[1].split("})", 1)[0]))
        suffixes = set(re.findall(r'"([A-Z_]+)"', segment.split("foreach (var suffix in new[]", 1)[1].split("})", 1)[0]))
        prefixes = set(re.findall(r'StartsWith\("([A-Z_]+)"', segment))
    return lambda value: (normalized := re.sub(r"[\s-]+", "_", value.strip()).upper()) in exact or any(
        normalized.endswith(s) for s in suffixes
    ) or any(normalized.startswith(p) for p in prefixes)


class BusyPendingAckFenceTests(unittest.TestCase):
    def test_both_native_owner_receipt_classifiers(self):
        for path, method, following in [
            (BRIDGE, "NativeOwnerStatusDenied(string? status)", "private static bool NativeResultExplicitlyDenied"),
            (LEGACY, "LegacyOwnerStatusDenied(string? status)", "private static bool LegacyOwnerDenial"),
        ]:
            with self.subTest(owner=method):
                denied = native_denial_classifier(path, method, following)
                for value in ("OWNER_BUSY", "ACK_STOP_PENDING", "PENDING", "BUSY", "native consent-pending", "provider-busy"):
                    with self.subTest(negative=value):
                        self.assertTrue(denied(value), value)
                for value in ("QUEUED", "RUNNING", "COMPLETED", "CANCEL_REQUESTED", "STOP_REQUESTED"):
                    with self.subTest(positive=value):
                        self.assertFalse(denied(value), value)


if __name__ == "__main__":
    unittest.main()
