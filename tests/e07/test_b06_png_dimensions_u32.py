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




def chunk(kind: bytes, data: bytes) -> bytes:
    """One authentic PNG chunk with its own CRC."""
    return (len(data).to_bytes(4,"big")+kind+data+
            (zlib.crc32(kind+data)&0xffffffff).to_bytes(4,"big"))


def full_png(w=1044,h=788) -> bytes:
    # RGBA PNG, one filter byte per row and a complete compressed pixel stream.
    pixels=(b"\x00"+b"\x00"*(w*4))*h
    return header(w,h)+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b"")

class B06PngIdentity(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/"D02_FINAL_SAME_SETUP.png"
    def put(self,data):
        self.path.write_bytes(data)
    def test_original_hwnd_capture(self):
        self.put(full_png())
        self.assertTrue(_capture_matches_png(self.path,[1044,788]))
    def test_other_resolution(self):
        self.put(full_png())
        self.assertFalse(_capture_matches_png(self.path,[800,600]))
    def test_reject_boolean_dimensions(self):
        self.put(full_png())
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

    def test_reject_ihdr_only_false_capture(self):
        self.put(header())
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_missing_iend(self):
        self.put(full_png()[:-12])
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_missing_idat(self):
        self.put(header()+chunk(b"IEND",b""))
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_trailing_bytes(self):
        self.put(full_png()+b"OLD_RUN_TRAILER")
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_corrupt_idat_crc(self):
        image=bytearray(full_png())
        image[50]^=1
        self.put(bytes(image))
        self.assertIsNone(_capture_png_dimensions(self.path))
    def test_reject_duplicate_ihdr(self):
        self.put(header()+header()[8:]+chunk(b"IDAT",b"x")+chunk(b"IEND",b""))
        self.assertIsNone(_capture_png_dimensions(self.path))

    def test_missing_photo(self):
        self.assertIsNone(_capture_png_dimensions(self.path))


if __name__=="__main__":
    unittest.main()
