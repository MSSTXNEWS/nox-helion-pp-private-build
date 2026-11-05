"""One offline ffmpeg owner contract: failed new film must preserve old MP4."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from integrations.creative.nox_fastpack import engine


class AtomicFilmReceipt(unittest.TestCase):
    def test_failed_render_preserves_previous_approved_mp4(self):
        with TemporaryDirectory() as d:
            studio=engine.Studio(d)
            project=studio._project("film")
            (project/"clip.mp4").write_bytes(b"CLIP")
            final=project/"NOX_MOVIE_FINAL.mp4"
            final.write_bytes(b"PREVIOUS_GOOD_FILM")
            def failed(args,timeout):
                destination=Path(args[-1])
                destination.write_bytes(b"INCOMPLETE")
                if destination.name.startswith(".NOX_MOVIE_"):
                    raise engine.StudioError("simulated ffmpeg error")
            with patch.object(engine.shutil,"which",return_value="ffmpeg"):
                studio._exec=failed
                with self.assertRaises(engine.StudioError):
                    studio.assemble("film",["clip.mp4"])
                self.assertEqual(final.read_bytes(),b"PREVIOUS_GOOD_FILM")
                self.assertFalse(list(project.glob(".NOX_MOVIE_*.mp4")))
                def completed(args,timeout):
                    destination=Path(args[-1])
                    destination.write_bytes(b"NEW_GOOD_FILM")
                studio._exec=completed
                result=studio.assemble("film",["clip.mp4"])
                self.assertEqual(result["status"],"RENDERED")
                self.assertEqual(final.read_bytes(),b"NEW_GOOD_FILM")


if __name__=="__main__":
    unittest.main()
