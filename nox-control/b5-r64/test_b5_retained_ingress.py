import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from test_b5_chain_guard import checkpoint, DIALOG, SESSION
import b5_retained_ingress as ingress


class RetainedIngressTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

    def pair(self, n, **kwargs):
        rows, (w, r, wp, rp) = checkpoint(n, **kwargs)
        files = []
        for data in (w, r):
            f = self.stack.enter_context(tempfile.TemporaryFile())
            f.write(data)
            f.flush()
            f.seek(1)
            files.append(f.fileno())
        return (*files, wp, rp)

    def load(self, *pairs):
        return ingress.load_retained_chain(dialog_id=DIALOG, session_id=SESSION,
                                           artifacts=pairs)

    def test_valid_prethird_and_terminal_preserve_offsets(self):
        pairs = tuple(self.pair(n) for n in (1, 2, 3))
        self.assertEqual([len(c[0]) for c in self.load(*pairs[:2])], [2, 4])
        self.assertEqual([len(c[0]) for c in self.load(*pairs)], [2, 4, 6])
        for pair in pairs:
            for fd in pair[:2]:
                self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 1)

    def test_reject_missing_or_reordered_history_and_nonadjacent_reuse(self):
        first, second, third = (self.pair(n) for n in (1, 2, 3))
        for bad in ((second,), (second, third), (second, first),
                    (first, second, self.pair(3, event="event-1")),
                    (first, second, self.pair(3, turn="turn-1"))):
            with self.subTest(count=len(bad)), self.assertRaises(ValueError):
                self.load(*bad)

    def test_cross_checkpoint_alias_and_wrong_pin(self):
        first, second = self.pair(1), self.pair(2)
        alias = os.dup(first[0])
        self.stack.callback(os.close, alias)
        with self.assertRaisesRegex(ValueError, "ALIAS"):
            self.load(first, (alias, *second[1:]))
        with self.assertRaisesRegex(ValueError, "REUSE"):
            self.load(first, (first[0], *second[1:]))
        with self.assertRaisesRegex(ValueError, "PIN"):
            self.load(first, (*second[:2], "0"*64, second[3]))

    def test_old_artifact_changed_during_later_read(self):
        first, second = self.pair(1), self.pair(2)
        original = ingress.load_pinned_s03_artifacts
        def load(**kwargs):
            result = original(**kwargs)
            if kwargs["sequence"] == 2:
                os.pwrite(first[0], b"X", 0)
            return result
        with patch.object(ingress, "load_pinned_s03_artifacts", side_effect=load):
            with self.assertRaisesRegex(ValueError, "CHANGED"):
                self.load(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
