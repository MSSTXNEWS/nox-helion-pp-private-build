"""One real-module test: bounded ComfyUI /view download, atomic import, no partial file.

All HTTP calls are patched to in-memory responses. This does not install
ComfyUI, render media, or constitute Windows E07.
"""
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from integrations.creative.nox_fastpack import engine


class BoundedMediaImport(unittest.TestCase):
    def test_atomic_bounded_media_from_local_comfyui(self):
        with TemporaryDirectory() as directory:
            studio=engine.Studio(Path(directory))
            asset={"filename":"scene.mp4","subfolder":"","type":"output","media":"videos"}
            studio.history=lambda task:{"status":"COMPLETE","files":[asset]}
            project="r31"
            for data,allowed in ((b"film",True),(b"abcdef",False),(b"",False)):
                with self.subTest(bytes=len(data),allowed=allowed):
                    with patch.object(engine,"MAX_CREATIVE_IMPORT_BYTES",5),\
                         patch.object(engine,"urlopen",return_value=io.BytesIO(data)):
                        if allowed:
                            reply=studio.import_asset("1234567890abcdef",asset,project)
                            self.assertEqual(reply["status"],"IMPORTED")
                            self.assertEqual(Path(reply["file"]).read_bytes(),data)
                        else:
                            with self.assertRaises(engine.StudioError):
                                studio.import_asset("1234567890abcdef",asset,project)
                    self.assertFalse(list((Path(directory)/"projects"/project/"assets").glob("*.download")))


if __name__=="__main__":
    unittest.main()
