"""3B05: root-anchored fd walk must reject ancestor swaps on actual mentor source."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[3] / 'integration' / 'owner_mini_source'
sys.path.insert(0, str(SOURCE))
import owner_dispatcher_mentor as mentor


class SkillAncestorSwap(unittest.TestCase):
    def test_existing_lock_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'memory/dispatcher_mentor').mkdir(parents=True)
            (root / 'memory/dispatcher_mentor/ledger.lock').write_bytes(b'LOCK')
            with patch.object(mentor, 'ROOT', root):
                fd = mentor._open_skill_evidence_readonly(
                    'memory/dispatcher_mentor/ledger.lock', os.O_RDONLY)
            with os.fdopen(fd, 'rb') as handle:
                self.assertEqual(handle.read(), b'LOCK')

    def test_ancestor_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'outside').mkdir()
            (root / 'outside/ledger.lock').write_bytes(b'secret')
            (root / 'memory').symlink_to(root / 'outside', target_is_directory=True)
            with patch.object(mentor, 'ROOT', root):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_SKILL_RANK_SYMLINK'):
                    mentor._open_skill_evidence_readonly('memory/ledger.lock', os.O_RDONLY)

    def test_leaf_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'memory').mkdir()
            (root / 'target').write_bytes(b'secret')
            (root / 'memory/ledger.lock').symlink_to(root / 'target')
            with patch.object(mentor, 'ROOT', root):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_SKILL_RANK_SYMLINK'):
                    mentor._open_skill_evidence_readonly('memory/ledger.lock', os.O_RDONLY)

    def test_parent_swap_after_preflight_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'memory').mkdir()
            (root / 'outside').mkdir()
            (root / 'outside/ledger.lock').write_bytes(b'secret')
            original_open = os.open
            changed = [False]

            def swap(path, flags, *args, **kwargs):
                if path == 'memory' and not changed[0]:
                    (root / 'memory').rmdir()
                    (root / 'memory').symlink_to(root / 'outside', target_is_directory=True)
                    changed[0] = True
                return original_open(path, flags, *args, **kwargs)

            with patch.object(mentor, 'ROOT', root), patch.object(os, 'open', side_effect=swap):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_SKILL_RANK_SYMLINK'):
                    mentor._open_skill_evidence_readonly('memory/ledger.lock', os.O_RDONLY)
            self.assertTrue(changed[0])

    def test_no_dotdot_or_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mentor, 'ROOT', Path(tmp)):
                for relative in ('../escape', 'memory/../escape', '/tmp/escape'):
                    with self.assertRaisesRegex(ValueError, 'HOLD_SKILL_RANK_PATH'):
                        mentor._open_skill_evidence_readonly(relative, os.O_RDONLY)

    def test_rankings_missing_ledger_still_holds_without_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'memory/dispatcher_mentor').mkdir(parents=True)
            (root / 'distill/queue').mkdir(parents=True)
            with patch.object(mentor, 'ROOT', root):
                view = mentor.read_verified_skill_rankings()
            self.assertEqual(view['state'], 'HOLD_NO_EXISTING_SKILL_LEDGER')
            self.assertFalse((root / 'memory/dispatcher_mentor/ledger.lock').exists())


if __name__ == '__main__':
    unittest.main()
