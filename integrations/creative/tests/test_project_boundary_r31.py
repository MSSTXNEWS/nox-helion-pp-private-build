"""One local test: existing NOX editable projects must not escape data root."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from integrations.creative.nox_fastpack.engine import Studio,StudioError


class ProjectBoundary(unittest.TestCase):
    def test_approved_project_and_redirected_folder(self):
        with TemporaryDirectory() as root:
            base=Path(root)/"data"
            outside=Path(root)/"other"
            outside.mkdir()
            studio=Studio(base)
            valid=studio._project("film01")
            self.assertTrue(valid.is_dir())
            shortcut=studio.projects/"redirect"
            try:shortcut.symlink_to(outside,target_is_directory=True)
            except (OSError,NotImplementedError):
                self.skipTest("Filesystem does not permit a symlink fixture")
            with self.assertRaises(StudioError):
                studio._project("redirect")
            self.assertFalse((outside/"storyboard.json").exists())


if __name__=="__main__":
    unittest.main()
