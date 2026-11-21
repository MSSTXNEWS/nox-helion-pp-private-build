import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qs6.events_bus import EventBus, serve


class BusT(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.p = os.path.join(self.td.name, "bus.jsonl")
        self.b = EventBus(self.p)

    def test_publish_read_filters(self):
        self.b.memory_found(["f:1"], "кофе", "t1")
        self.b.mode_changed("тихий", "работа", "команда")
        self.b.reply_started("t1")
        self.b.reply_finished("t1", 42)
        evs = self.b.read()
        self.assertEqual([e["seq"] for e in evs], [1, 2, 3, 4])
        self.assertEqual([e["type"] for e in evs], ["memory.found", "mode.changed", "reply.started", "reply.finished"])
        self.assertEqual(self.b.read(2)[0]["type"], "reply.started")
        self.assertEqual(len(self.b.read(types=["mode.changed"])), 1)
        self.assertEqual(self.b.latest_seq(), 4)
        self.assertEqual(self.b.read(limit=2)[-1]["seq"], 2)
        with self.assertRaises(ValueError):
            self.b.publish("")

    def test_seq_continues_across_instances_and_bad_lines(self):
        self.b.publish("a")
        with open(self.p, "a") as f:
            f.write("мусор\n")
        b2 = EventBus(self.p)
        self.assertEqual(b2.publish("b")["seq"], 2)
        self.assertEqual([e["type"] for e in b2.read()], ["a", "b"])

    def test_poll_timeout_and_wakeup(self):
        t0 = time.time()
        r = self.b.poll(0, timeout=0.3, interval=0.05)
        self.assertTrue(r["timeout"]); self.assertGreaterEqual(time.time() - t0, 0.25)
        self.assertEqual(r["events"], [])
        threading.Timer(0.2, lambda: self.b.publish("reply.started", {"turn_id": "x"})).start()
        r = self.b.poll(timeout=3, interval=0.05)       # since=None: только будущие
        self.assertFalse(r["timeout"]); self.assertEqual(r["events"][0]["data"]["turn_id"], "x")
        self.assertEqual(r["last_seq"], 1)
        threading.Timer(0.2, lambda: (self.b.publish("x1"), self.b.publish("mode.changed"))).start()
        r = self.b.poll(1, types=["mode.changed"], timeout=3, interval=0.05)
        self.assertEqual([e["type"] for e in r["events"]], ["mode.changed"])

    def test_old_events_returned_immediately(self):
        self.b.publish("a"); self.b.publish("b")
        t0 = time.time()
        r = self.b.poll(0, timeout=5)
        self.assertLess(time.time() - t0, 1)
        self.assertEqual(r["last_seq"], 2)

    def test_rotation_keeps_seq(self):
        b = EventBus(self.p, max_bytes=600)
        last = 0
        for i in range(30):
            last = b.publish("t", {"i": i, "pad": "x" * 30})["seq"]
        self.assertTrue(os.path.exists(self.p + ".1"))
        self.assertGreater(b.latest_seq(), 30)           # +служебные bus.rotated
        seqs = [e["seq"] for e in b.read()]
        self.assertEqual(seqs, sorted(seqs))
        self.assertLess(os.path.getsize(self.p), 1500)

    def test_concurrent_writers_unique_seq(self):
        ths = [threading.Thread(target=lambda: [self.b.publish("c") for _ in range(20)]) for _ in range(5)]
        [t.start() for t in ths]; [t.join() for t in ths]
        seqs = [e["seq"] for e in self.b.read(limit=1000)]
        self.assertEqual(seqs, list(range(1, 101)))

    def test_http_long_poll(self):
        srv = serve(self.b, port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close); self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d/events" % srv.server_port
        threading.Timer(0.2, lambda: self.b.publish("memory.found", {"refs": ["f:1"]})).start()
        with urllib.request.urlopen(base + "?timeout=3&types=memory.found", timeout=6) as r:
            d = json.loads(r.read())
        self.assertEqual(d["events"][0]["type"], "memory.found")
        with urllib.request.urlopen(base + "?since=0&timeout=1", timeout=6) as r:
            self.assertEqual(len(json.loads(r.read())["events"]), 1)
        with urllib.request.urlopen(base + "?since=1&timeout=0.2", timeout=6) as r:
            self.assertTrue(json.loads(r.read())["timeout"])


if __name__ == "__main__":
    unittest.main()
