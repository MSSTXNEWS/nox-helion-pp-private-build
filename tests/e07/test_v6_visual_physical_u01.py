"""Fail-closed source regression, never a substitute for Windows screenshot/E07."""
from __future__ import annotations
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
import zlib

class Hold(RuntimeError):
    pass

def require(ok, code):
    if not ok:
        raise Hold(code)

def sha256(p):
    with open(p,'rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

stub = types.ModuleType('independent_setup_e07')
stub.Hold, stub.require, stub.sha256 = Hold, require, sha256
stub.clean_file = lambda p: p.is_file() and not p.is_symlink()
sys.modules[stub.__name__] = stub
frozen = types.ModuleType('probe_full_d02_722399_u13')
frozen.SOURCE = 'ffca9aaedce9d90750dfb212aabcdfd970162150'
frozen.SETUP_SHA = '722399ee3d7794a7aa38d93d933026e015fd29b0d8a60fd431b0bc494040a6bc'
frozen.BUILDID = 'NOX-V16-99fce33d002363f6b3e9b9cf'
sys.modules[frozen.__name__] = frozen
root=Path(__file__).resolve().parents[2]
path=root/'coordination/e07/probe_v6_visual_physical_u01.py'
spec=importlib.util.spec_from_file_location('nox_v6_visual_u01',path)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def png(width, height, *, noise=True):
    # Correct PNG signature + IHDR, independent of Pillow or external assets.
    def chunk(tag,data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    ihdr=struct.pack('>IIBBBBB',width,height,8,2,0,0,0)
    if width*height<4_000_000:
        rows = b''.join(b'\x00'+(os.urandom(width*3) if noise else b'\x00'*width*3) for _ in range(height))
        data=zlib.compress(rows,6)
    else:
        data=b''
    return mod.PNG_SIGNATURE+chunk(b'IHDR',ihdr)+chunk(b'IDAT',data)+chunk(b'IEND',b'')

class V6VisualPhysicalSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)/'capture.png'
    def test_nonaligned_noise_capture_does_not_claim_visual_approval(self):
        self.p.write_bytes(png(800,600))
        proof=mod.checked_png(self.p)
        self.assertEqual(proof['physical_capture'],'PASS')
        self.assertEqual(proof['independent_visual_review'],'NOT_RUN')
        self.assertEqual(proof['reduced_motion'],'NOT_TESTED')
        self.assertEqual(proof['width'],800)
        self.assertEqual(proof['sha256'],sha256(self.p))
    def test_blank_small_png_must_hold(self):
        self.p.write_bytes(png(800,600,noise=False))
        with self.assertRaisesRegex(Hold,'EMPTY_OR_UNTRUSTED'):
            mod.checked_png(self.p)
    def test_wrong_header_must_hold(self):
        self.p.write_bytes(b'X'*40000)
        with self.assertRaisesRegex(Hold,'NOT_PNG'):
            mod.checked_png(self.p)
    def test_undersized_dimensions_must_hold(self):
        self.p.write_bytes(png(500,600))
        with self.assertRaisesRegex(Hold,'DIMENSIONS'):
            mod.checked_png(self.p)
    def test_no_file_must_hold(self):
        with self.assertRaisesRegex(Hold,'EMPTY_OR_UNTRUSTED'):
            mod.checked_png(self.p)
    def test_no_visual_approval_by_source_only(self):
        text=path.read_text('utf-8')
        self.assertIn('"independent_e07_10_10": "HOLD"',text)
        self.assertIn('"visual_e07": "HOLD"',text)
        self.assertIn('frozen.candidate(args.artifact_dir)',text)
        self.assertIn('e07.gui_hwnd(',text)
        self.assertIn('original_observer(hwnd)',text)
        self.assertIn('e07.manifest_owner(install)',text)
        self.assertIn('GetForegroundWindow()',text)
    def test_linux_cannot_forge_windows_screenshot(self):
        if sys.platform != 'win32':
            with self.assertRaisesRegex(Hold,'ORIGINAL_WINDOWS_HWND'):
                mod.capture_window(1234,self.p)

    def test_real_fx_cycle_receipt_is_narrow(self):
        got = mod.evaluate_fx_cycle({
            "initial": "FX BALANCED",
            "observed": ["FX MAX", "FX ECO", "FX BALANCED"],
            "invocations": 3,
        })
        self.assertEqual(got["fx_control"], "PASS")
        self.assertEqual(got["actual_invoke_transitions"], 3)
        self.assertEqual(got["reduced_motion"], "NOT_TESTED")
        self.assertEqual(got["independent_visual_review"], "NOT_RUN")
        self.assertNotIn("release_accepted", got)

    def test_fake_fx_count_order_label_and_extra_claims_hold(self):
        good = {"initial": "FX BALANCED",
                "observed": ["FX MAX", "FX ECO", "FX BALANCED"],
                "invocations": 3}
        bad = [
            {**good, "initial": "FX MAX"},
            {**good, "observed": ["FX MAX", "FX MAX", "FX BALANCED"]},
            {**good, "observed": ["FX MAX", "FX ECO"]},
            {**good, "invocations": True},
            {**good, "invocations": 2},
            {**good, "release_accepted": True},
            {**good, "observed": "FX MAX,FX ECO,FX BALANCED"},
            {"initial": "FX BALANCED", "invocations": 3},
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaisesRegex(Hold, "V6_FX_PHYSICAL_TRANSITION_HOLD"):
                mod.evaluate_fx_cycle(item)

    def test_real_fx_script_requires_unique_native_invoke_three_times(self):
        source = path.read_text("utf-8")
        self.assertIn("GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)", source)
        self.assertIn("$pattern.Invoke()", source)
        self.assertIn("foreach($expected in @('FX MAX','FX ECO','FX BALANCED'))", source)
        self.assertIn("[System.Windows.Automation.PropertyCondition]::new(", source)
        self.assertIn("$foundControls.Count -ne 1", source)
        self.assertNotIn("$matches", source.lower())
        self.assertIn("fx_checks.append(probe_fx_cycle(hwnd))", source)
        self.assertIn('"physical_fx_cycle": fx_checks[0]', source)
        self.assertIn('"independent_e07_10_10": "HOLD"', source)

    def test_linux_cannot_forge_fx_invoke(self):
        if sys.platform != "win32":
            with self.assertRaisesRegex(Hold, "V6_FX_ORIGINAL_WINDOWS_HWND_REQUIRED"):
                mod.probe_fx_cycle(42)


if __name__=='__main__':
    unittest.main()
