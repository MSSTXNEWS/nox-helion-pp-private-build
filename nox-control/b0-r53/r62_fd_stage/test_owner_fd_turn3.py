import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import owner_chat_probe as probe
from test_chain_bound import cp, inputs, finish_args
from b0_owner_fd_turn3 import prepare_owner_fd_turn3


class OwnerFDCompositionTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.pairs = tuple(self.pair(n) for n in (1, 2, 3))

    def pair(self, n):
        _, (w, r, wp, rp) = cp(n)
        fds = []
        for raw in (w, r):
            f = self.stack.enter_context(tempfile.TemporaryFile())
            f.write(raw)
            f.flush()
            f.seek(1)
            fds.append(f.fileno())
        return (*fds, wp, rp)

    def prepare(self, pairs=None, mutate=None, expected_gets=1):
        kw, history = inputs()
        for name in ("canonical_rows", "prior_witnesses"):
            kw.pop(name)
        with patch.object(probe, "require_preturn_owner_binding"), \
             patch.object(probe, "owner_readback_json", return_value=history) as get, \
             patch.object(probe, "require_postturn_owner_binding", side_effect=mutate):
            try:
                return prepare_owner_fd_turn3(artifacts=self.pairs[:2] if pairs is None else pairs, **kw)
            finally:
                self.assertEqual(get.call_count, expected_gets)

    def args(self):
        return {k:v for k,v in finish_args().items() if k not in ("canonical_rows", "witnesses")}

    def test_real_fd_roundtrip_one_get_one_terminal(self):
        evidence = self.prepare()
        self.assertEqual(evidence.finish(artifacts=self.pairs, **self.args()), "RESUME_EVIDENCE_MATCHED")
        self.assertEqual(evidence.finish(artifacts=self.pairs, **self.args()), "HOLD_RESUME_ALREADY_CONSUMED")
        for pair in self.pairs:
            for fd in pair[:2]:
                self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 1)

    def test_missing_or_wrong_pin_stops_before_get(self):
        first, second, _ = self.pairs
        for pairs in ((second,), (first, (*second[:2], "0"*64, second[3]))):
            with self.assertRaises(ValueError):
                self.prepare(pairs, expected_gets=0)

    def test_mutation_during_owner_get_fails_closed(self):
        with self.assertRaises(ValueError):
            self.prepare(mutate=lambda _: os.pwrite(self.pairs[0][0], b"X", 0))

    def test_terminal_tamper_consumes_without_retry(self):
        evidence = self.prepare()
        os.pwrite(self.pairs[0][0], b"X", 0)
        self.assertEqual(evidence.finish(artifacts=self.pairs, **self.args()), "HOLD_B0_TERMINAL_FD_CHAIN")
        self.assertEqual(evidence.finish(artifacts=self.pairs, **self.args()), "HOLD_RESUME_ALREADY_CONSUMED")

    def test_terminal_cannot_override_fd_rows(self):
        evidence = self.prepare()
        self.assertEqual(evidence.finish(artifacts=self.pairs, canonical_rows=[], **self.args()), "HOLD_B0_TERMINAL_FD_OVERRIDE")
        self.assertEqual(evidence.finish(artifacts=self.pairs, **self.args()), "HOLD_RESUME_ALREADY_CONSUMED")
