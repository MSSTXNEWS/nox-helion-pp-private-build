"""NOX existing local bridge with bounded read-only discovery endpoints."""
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import server_mega as old
import nox_probe
PORT=18775
old.PORT=PORT
old.base.PORT=PORT
class Handler(old.Handler):
    def do_GET(self):
        route=urlsplit(self.path).path
        if route=='/api/nox/discover':return self._json(200,nox_probe.status())
        if route=='/api/nox/pages':
            return self._json(200,{'pages':['index.html','chat.html','training.html','models.html','memory.html','system.html','install.html','projects.html','settings.html'],
                       'status':'ROUTES_AVAILABLE','note':'Function contracts may remain HOLD.'})
        return super().do_GET()
if __name__=='__main__':
    print('NOX existing bridge candidate http://127.0.0.1:18775',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever(poll_interval=.25)