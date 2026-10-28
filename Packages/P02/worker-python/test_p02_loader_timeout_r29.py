"""TIMEOUT, STOP and connection failure remain distinct installer outcomes."""
import io
import threading
import unittest
import urllib.error
from unittest.mock import patch
import p02_runtime as runtime
from p02_chat_bridge import ChatBridge

class Store:
    def __init__(self):self.rows=[]
    def history(self,*args):return []
    def add_message(self,*args,**kwargs):self.rows.append(args[-2:])

class TimeoutResponse:
    def __iter__(self):
        yield b'{"message":{"content":"partial"},"done":false}\n'
        raise TimeoutError('socket wait expired')
    def close(self):pass

class TimeoutClient(runtime.OllamaClient):
    def models(self):return ['installed']
    def _open(self,*args):return TimeoutResponse()

class TimeoutContract(unittest.TestCase):
    def test_socket_timeout_has_typed_provider_outcome(self):
        for error in (TimeoutError(),urllib.error.URLError(TimeoutError())):
            with self.subTest(error=type(error).__name__),patch.object(runtime._OPENER,'open',side_effect=error):
                with self.assertRaises(runtime.P02Error) as failure:runtime.OllamaClient().models()
                self.assertEqual(type(failure.exception).__name__,'ProviderTimeout')

    def test_model_list_read_timeout_has_same_typed_outcome(self):
        class Response(io.BytesIO):
            def read(self,*args):raise TimeoutError()
        with patch.object(runtime._OPENER,'open',return_value=Response()):
            with self.assertRaises(runtime.P02Error) as failure:runtime.OllamaClient().models()
            self.assertEqual(type(failure.exception).__name__,'ProviderTimeout')

    def test_stream_timeout_emits_timeout_without_assistant_success(self):
        store=Store();events=list(ChatBridge(store,TimeoutClient()).send('t','p','c','installed','hello'))
        self.assertEqual([e['type'] for e in events],['chat.start','chat.delta','chat.error'])
        self.assertEqual(events[-1]['code'],'TIMEOUT');self.assertEqual(store.rows,[('user','hello')])

    def test_stop_after_partial_frame_remains_stop_even_if_socket_times_out(self):
        store=Store();stop=threading.Event()
        events=ChatBridge(store,TimeoutClient()).send('t','p','c','installed','hello',stop)
        next(events);next(events);stop.set();tail=list(events)
        self.assertEqual(tail[-1]['code'],'STOP');self.assertEqual(store.rows,[('user','hello')])

    def test_refused_connection_is_not_mislabeled_timeout(self):
        with patch.object(runtime._OPENER,'open',side_effect=urllib.error.URLError(ConnectionRefusedError())):
            with self.assertRaises(runtime.P02Error) as failure:runtime.OllamaClient().models()
            self.assertEqual(type(failure.exception).__name__,'P02Error')

    def test_invalid_timeout_budgets_do_not_reach_host_transport(self):
        for value in (True,False,float('nan'),float('inf'),'30',None,0,-1,601):
            with self.subTest(value=value),self.assertRaises(ValueError):runtime.OllamaClient(timeout=value)

if __name__=='__main__':unittest.main()
