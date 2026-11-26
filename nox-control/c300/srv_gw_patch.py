import re,sys,shutil,time,os
G="/workspace/nox/advisors/gateway.py"
s=open(G,encoding="utf-8").read()
if "JRN_P3" in s: print("already patched"); sys.exit(0)
shutil.copy(G,G+".bak_jrn_%d"%int(time.time()))
helper='''
# JRN_P3: журнал запросов шлюза без содержимого (время, провайдер, prio, категория), ротация 7 дней
JRN_DIR = '/workspace/nox/state/gw_journal'
_JRN_CAT = [('code', r'(?i)\\b(python|код|функци|скрипт|bug|ошибк\\w* в коде|sql|html|css|javascript|def )\\b|```'),
            ('math', r'(?i)(сколько будет|\\d+\\s*[*/+x×-]\\s*\\d+|уравнени|интеграл|производн)'),
            ('translate', r'(?i)(переведи|перевод|translate)'),
            ('image', r'(?i)(нарису|картинк|изображени|рисун|draw|image)'),
            ('news', r'(?i)(новост|погод|курс\\b|сегодня|сейчас в)'),
            ('smalltalk', r'(?i)^\\W*(привет|здравствуй|как дела|hi\\b|hello|спасибо)')]
def _jrn_cat(body):
    try:
        t = ' '.join(str(x.get('content', '')) for x in (body.get('messages') or body.get('prompt') and [{'content': body.get('prompt')}] or []) if isinstance(x, dict))
        if PRIVATE_TOPICS.search(t): return 'private'
        for n, rx in _JRN_CAT:
            if re.search(rx, t): return n
        return 'other'
    except Exception: return 'unknown'
def _jrn(path, body, code, out):
    try:
        os.makedirs(JRN_DIR, exist_ok=True)
        nx = (out.get('nox') or {}) if isinstance(out, dict) else {}
        rec = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'route': path.split('?')[0][-24:], 'code': code, 'provider': nx.get('provider') or ('none' if code != 200 else ''),
               'local': bool(nx.get('local')), 'cached': bool(nx.get('cached')), 'prio': int(body.get('x_nox_prio', 5)), 'cat': _jrn_cat(body), 'ms': nx.get('ms')}
        fn = os.path.join(JRN_DIR, time.strftime('%Y-%m-%d') + '.jsonl')
        first = not os.path.exists(fn)
        with open(fn, 'a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\\n')
        if first:
            for o in os.listdir(JRN_DIR):
                p = os.path.join(JRN_DIR, o)
                if o.endswith('.jsonl') and time.time() - os.path.getmtime(p) > 7 * 86400:
                    try: os.remove(p)
                    except Exception: pass
    except Exception: pass
'''
anchor="class H(BaseHTTPRequestHandler):"
assert anchor in s
s=s.replace(anchor,helper+"\n"+anchor,1)
old="        code, out = (route or chat)(body); self.send(code, out)"
assert old in s
s=s.replace(old,"        code, out = (route or chat)(body); _jrn(self.path, body, code, out); self.send(code, out)",1)
open(G,"w",encoding="utf-8").write(s)
import py_compile; py_compile.compile(G,doraise=True); print("patched ok")
