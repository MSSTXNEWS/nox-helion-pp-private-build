import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from owner_secret_staging import create_secret_file


class SecretStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_context.cleanup)
        self.root = Path(self.temp_context.name)
        self.run_id = "123456"
        self.attempt = "1"
        self.name = f"nox2-s03-{self.run_id}-{self.attempt}"
        self.path = self.root / self.name
        self.env_patch = mock.patch.dict(os.environ, {
            "GITHUB_RUN_ID": self.run_id,
            "GITHUB_RUN_ATTEMPT": self.attempt,
        }, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_preexisting_regular_file_is_not_replaced(self):
        self.path.write_text("sentinel", encoding="ascii")
        self.path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "HOLD_CREDENTIAL_PATH_EXISTS"):
            create_secret_file(self.root, self.path, "new-secret")
        self.assertEqual(self.path.read_text(encoding="ascii"), "sentinel")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)

    def test_preexisting_symlink_is_not_followed_or_overwritten(self):
        destination = self.root / "target"
        destination.write_text("sentinel", encoding="ascii")
        self.path.symlink_to(destination)
        with self.assertRaisesRegex(RuntimeError, "HOLD_CREDENTIAL_PATH_EXISTS"):
            create_secret_file(self.root, self.path, "new-secret")
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(destination.read_text(encoding="ascii"), "sentinel")

    def test_competing_creators_have_one_atomic_winner(self):
        barrier = threading.Barrier(2)
        outcomes = []

        def attempt(secret):
            barrier.wait()
            try:
                create_secret_file(self.root, self.path, secret)
                outcomes.append(("created", secret))
            except RuntimeError as exc:
                outcomes.append((str(exc), secret))

        threads = [threading.Thread(target=attempt, args=(secret,))
                   for secret in ("token-alpha", "token-beta")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(status == "created" for status, _ in outcomes), 1)
        self.assertEqual(sum(status == "HOLD_CREDENTIAL_PATH_EXISTS" for status, _ in outcomes), 1)
        self.assertIn(self.path.read_text(encoding="ascii"), {"token-alpha", "token-beta"})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)

    def test_symlinked_runner_temp_is_rejected(self):
        outer = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: outer.rmdir())
        link = outer / "temp-link"
        link.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(link.unlink)
        with self.assertRaisesRegex(RuntimeError, "HOLD_RUNNER_TEMP_DIRECTORY"):
            create_secret_file(link, link / self.name, "token")
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
