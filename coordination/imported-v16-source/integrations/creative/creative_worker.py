"""NOX Creative Worker: JSON-lines stdio, no public listener, no shell execution.
Bundled with the R13 NSIS payload as an on-demand hidden child worker.
"""
import json
import os
import sys
import threading
from pathlib import Path

from nox_fastpack.engine import Studio, StudioError

WRITE = threading.RLock()
THREADS = set()
THREADS_LOCK = threading.Lock()
MAX_REQUEST = 262_144


def emit(request_id, ok, data=None, error=None):
    message = {'request_id': request_id, 'ok': ok}
    if ok: message['data'] = data
    else: message['error'] = str(error or 'Unknown creative adapter error')[:1600]
    with WRITE:
        sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(',', ':'))+'\n')
        sys.stdout.flush()


def serve_line(studio, line):
    request_id = None
    try:
        if len(line.encode('utf-8')) > MAX_REQUEST:
            raise StudioError('Native creative request exceeds 256 KiB')
        request = json.loads(line)
        if not isinstance(request, dict): raise StudioError('Invalid request object')
        request_id = request.get('request_id')
        payload = request.get('payload')
        if not isinstance(request_id, str) or len(request_id)>70 or not isinstance(payload, dict):
            raise StudioError('Invalid request envelope')
        result = studio.dispatch(payload)
        emit(request_id, True, result)
    except (StudioError, TypeError, ValueError, OSError) as exc:
        emit(request_id, False, error=str(exc))
    except Exception as exc:
        emit(request_id, False, error='Engine failure: '+type(exc).__name__)


def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin,"reconfigure"):sys.stdin.reconfigure(encoding="utf-8")
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args)!=1 or not args[0]:
        sys.stderr.write('NOX_CreativeWorker requires one user-data root argument\n')
        return 2
    root=Path(args[0]).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    studio=Studio(root)
    for line in sys.stdin:
        if not line.strip():continue
        # STOP must not wait behind long FFmpeg / Ollama jobs.
        with THREADS_LOCK:
            THREADS.difference_update(t for t in THREADS if not t.is_alive())
            if len(THREADS)>=16:
                emit(None,False,error='Worker task limit reached')
                continue
            thread=threading.Thread(target=serve_line,args=(studio,line),daemon=True)
            THREADS.add(thread)
        thread.start()
    studio.stop()
    with THREADS_LOCK:
        current=list(THREADS)
    for thread in current:thread.join(timeout=1)
    return 0


if __name__=='__main__':raise SystemExit(main())
