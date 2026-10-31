"""Wire existing PACK01 chat and original OllamaClient to the ONE S03 store.

No new transport, history tables or downloader. The native owner supplies the
already scoped store adapter and authenticated NativeSession objects.
"""
from __future__ import annotations
import threading
from dataclasses import replace
from contextlib import contextmanager
from nox_native_bridge import ExistingP02Adapter, HostDenied, HostHold
from p02_runtime import OllamaClient, P02Error, P02Timeout, Cancelled
from p02_native_ingress import ProtocolHold


class OneHostP02(ExistingP02Adapter):
    def __init__(self, store, *, event_sink=None, client=None):
        super().__init__(client if client is not None else OllamaClient(), store,
                         event_sink=event_sink)
        self._selected = None
        self._selection_lock = threading.RLock()
        self.stop_event = threading.Event()

    @contextmanager
    def selection_transaction(self):
        with self._selection_lock:
            yield self

    def selected_model(self):
        with self._selection_lock:
            return self._selected

    def stop_requested(self):
        return self.stop_event.is_set()

    def _scope(self, session, args):
        if type(args) is not dict:
            raise HostDenied('Object payload required')
        payload = dict(args)
        if 'core_id' in payload or 'persona_id' in payload:
            resolver = getattr(self.store, 'resolve_chat_id', None)
            if not callable(resolver):
                raise HostHold('CANONICAL_PERSONA_SCOPE_RESOLVER_REQUIRED')
            chat_id = resolver(payload.pop('core_id', None), payload.pop('persona_id', None))
            session = replace(session, chat_id=chat_id)
            session.validate()
        return session, payload

    def list_models(self, session, args):
        session, args = self._scope(session, args)
        if set(args) - {'model'}:
            raise HostDenied('Only installed model selection is accepted')
        offline = False
        try:
            models = self.client.models()
        except (P02Error, OSError, TimeoutError):
            models, offline = [], True
        if (type(models) is not list or len(models) > 4096 or
                any(type(x) is not str or not 0 < len(x) <= 256 for x in models)
                or len(models) != len(set(models))):
            raise HostHold('Invalid installed model inventory')
        requested = args.get('model')
        if requested is not None:
            if type(requested) is not str or requested not in models:
                raise HostHold('Selected model not installed')
            lineage_gate = getattr(self.store, 'assert_model_switch_safe', None)
            if not callable(lineage_gate):
                raise HostHold('SEED_LINEAGE_GATE_REQUIRED')
            lineage_gate()
            with self._selection_lock:
                self._selected = requested
        with self._selection_lock:
            if self._selected not in models:
                self._selected = None
            selected = self._selected
        return {'models': models, 'selectedModel': selected,
                'provider_state': 'OFFLINE' if offline else ('READY' if models else 'NO_LOCAL_MODEL'),
                'source': 'EXISTING_P02_OLLAMA',
                'lineage': self.store.lineage_status() if callable(
                    getattr(self.store, 'lineage_status', None)) else {'status':'HOLD'}}

    def history(self, session, args):
        # Existing S03 remains readable when Ollama has no models or is offline.
        session, args = self._scope(session, args)
        return super().history(session, args)

    def chat(self, session, args):
        session, payload = self._scope(session, args)
        if set(payload) - {'text','model'}:
            raise HostDenied('Unknown chat payload fields')
        if type(payload.get('text')) is not str or not 0 < len(payload['text']) <= 8000:
            raise HostDenied('Original chat prompt limit is 8000 characters')
        explicit = payload.get('model')
        if explicit is not None:
            self.list_models(session, {'model': explicit})
        model = self.selected_model()
        if model is None:
            raise HostHold('Select an installed local model before chat')
        payload['model'] = model
        self.stop_event.clear()
        try:
            with self.store.model_context(model):
                return super().chat(session, payload)
        except P02Timeout as exc:
            raise ProtocolHold('NATIVE_CHAT_TIMEOUT') from exc
        except Cancelled as exc:
            raise ProtocolHold('NATIVE_CHAT_STOP') from exc
        except HostDenied as exc:
            if self.stop_requested():
                raise ProtocolHold('NATIVE_CHAT_STOP') from exc
            raise

    def stop(self, session, args):
        self.stop_event.set()
        return super().stop(session, args)

    def create_coder(self, authorize):
        from nox_selfbuilder.p02_coder import P02Coder
        return P02Coder(ollama=self.client, model_name=self.selected_model,
                        authorize=authorize, stop_requested=self.stop_requested,
                        stop_event=self.stop_event)


def create_onehost_p02(store, *, event_sink=None, client=None):
    return OneHostP02(store, event_sink=event_sink, client=client)
