"""SOURCE_ONLY: original D02 PNG header CRC and dimensions match physical UIA."""
from __future__ import annotations
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"coordination"/"e07"))
from probe_final_same_setup import _capture_png_dimensions, _capture_matches_png


def header(w=1044,h=788,*,bad_crc=False):
    fields=struct.pack(">IIBBBBB",w,h,8,6,0,0,0)
    crc=zlib.crc32(b"IHDR"+fields)&0xffffffff
    return b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+fields+struct.pack(">I",crc ^ int(bad_crc))


class B06PngIdentity(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/"D02_FINAL_SAME_SETUP.png"
    def put(self,data):
        self.path.write_bytes(data)
    def test_original_hwnd_capture(self):
        self.put(header())
        self.assertTrue(_capture_matches_png(self.path,[1044,788]))
    def test_other_resolution(self):
        self.put(header())
        self.assertFalse(_capture_matches_png(self.path,[800,600]))
    def test_reject_boolean_dimensions(self):
        self.put(header())
        self.assertFalse(_capture_matches_png(self.path,[True,788]))
    def test_reject_bad_crc(self):
        self.put(header(bad_crc=True))
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_bad_signature(self):
        self.put(b"X"+header()[1:])
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_fake_ihdr(self):
        self.put(header()[:12]+b"FAKE"+header()[16:])
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_truncated(self):
        self.put(header()[:24])
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_unbounded(self):
        self.put(header(8193,788))
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_missing_photo(self):
        self.assertIsNone(_capture_png_dimensions(self.path))


if __name__=="__main__":
    unittest.main()
