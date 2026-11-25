import unittest
from b0_http_chunked_r76 import write_chunked_sse
from b0_named_delta_encoder import encode_native_delta

FRAME = {"type":"delta","event_id":"existing:2:1","text":"Привет 🌞\n¡Hola!"}
FINAL = b"0\r\n\r\n"


class Source:
    def __init__(self, fault=False, close_fault=False):
        self.reads = self.closes = 0
        self.fault, self.close_fault = fault, close_fault
    def __iter__(self):
        return self
    def __next__(self):
        self.reads += 1
        if self.reads == 1:
            return FRAME
        if self.fault:
            raise OSError("upstream")
        raise StopIteration
    def close(self):
        self.closes += 1
        if self.close_fault:
            raise OSError("close")


class Wire:
    def __init__(self, fault=None):
        self.fault = fault
        self.writes = []
        self.aborts = self.flushes = 0
    def headers(self):
        if self.fault == "headers":
            raise OSError("headers")
        if self.fault == "callback_eof":
            raise StopIteration
    def write(self, b):
        if self.fault == "write":
            raise OSError("write")
        self.writes.append(b)
        if self.fault == "short":
            return len(b)-1
        if self.fault == "unknown":
            return None
        if self.fault == "final_short" and b == FINAL:
            return 0
        return len(b)
    def flush(self):
        self.flushes += 1
        if self.fault == "flush":
            raise OSError("flush")
    def abort(self):
        self.aborts += 1
    def run(self, source):
        return write_chunked_sse(source, start_headers=self.headers,
            write=self.write, flush=self.flush, abort_transport=self.abort)


class WriterTest(unittest.TestCase):
    def test_clean_exact_bytes(self):
        s,w = Source(), Wire()
        self.assertIsNone(w.run(s))
        b=encode_native_delta(FRAME)
        self.assertEqual(w.writes, [("%x\r\n" % len(b)).encode()+b+b"\r\n",FINAL])
        self.assertEqual((s.reads,s.closes,w.aborts,w.flushes),(2,1,0,2))

    def test_faults_before_terminal(self):
        for fault in ("headers","callback_eof","write","short","unknown","flush",
                      "upstream","close"):
            with self.subTest(fault=fault):
                s,w=Source(fault=="upstream",fault=="close"),Wire(fault)
                with self.assertRaises((OSError,RuntimeError)) as err:
                    w.run(s)
                if fault=="callback_eof":
                    self.assertIn("FALSE_EOF",str(err.exception))
                self.assertEqual((s.closes,w.aborts),(1,1))
                self.assertNotIn(FINAL,w.writes)
                self.assertEqual(s.reads,0 if fault in ("headers","callback_eof") else
                                 2 if fault in ("upstream","close") else 1)

    def test_uncertain_final_write_aborts_not_retries(self):
        s,w=Source(),Wire("final_short")
        with self.assertRaisesRegex(OSError,"SHORT_WRITE"):
            w.run(s)
        self.assertEqual((s.closes,w.aborts,w.writes.count(FINAL)),(1,1,1))


if __name__=="__main__":
    unittest.main()
