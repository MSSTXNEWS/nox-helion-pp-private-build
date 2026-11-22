"""Отдельный процесс «Что NOX вспомнил»: Recall API на 127.0.0.1:8095 (NOX_RECALL_PORT).
Запуск: cd nox-control && NOX_MEMORY_DB=/root/nox/memory/s03.db python3 -m qs6.recall_server
Слушает только loopback; наружу его отдаёт веб-сервер как /memory/*. Если БД нет, процесс не стартует (код 2)."""
import os
import sys


def _wow_mem():
    d = os.environ.get("NOX_WOW7_MEM") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wow7", "mem")
    if os.path.isdir(d) and d not in sys.path:
        sys.path.append(d)


def build(env=None):
    from .events_bus import EventBus
    from .memory_search import MemorySearch
    from .recall_api import Recall, serve
    from .s03_store import Store
    env = os.environ if env is None else env
    db = (env.get("NOX_MEMORY_DB") or "").strip()
    if not db or not os.path.isfile(db):
        raise SystemExit("recall_server: NOX_MEMORY_DB не задан или файла нет (%r)" % db)
    host = (env.get("NOX_RECALL_HOST") or "127.0.0.1").strip()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("recall_server: только loopback, а не %r" % host)
    port = int(env.get("NOX_RECALL_PORT") or 8095)
    store = Store(db)
    ev = (env.get("NOX_EVENTS") or "").strip() or os.path.join(os.path.dirname(os.path.abspath(db)), "events.jsonl")
    recall = Recall(store, MemorySearch(store), bus=EventBus(ev))
    _wow_mem()
    try:
        from correction import CorrectionAPI     # MEM-02: правка/отзыв проверяются перечитыванием, + get/revoke/restore/revision
        recall = CorrectionAPI(recall)
    except Exception as ex:
        print("recall_server: ВНИМАНИЕ, CorrectionAPI не загружен (%s): правки и отзывы НЕ проверяются" % ex, file=sys.stderr, flush=True)
    return serve(recall, host, port)


if __name__ == "__main__":
    srv = build()
    print("recall_api %s:%d db=%s" % (srv.server_address[0], srv.server_address[1], os.environ.get("NOX_MEMORY_DB")), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
