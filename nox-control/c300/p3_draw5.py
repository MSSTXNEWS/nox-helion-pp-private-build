import sys, json, time, base64, urllib.request, re
sys.path.insert(0, "/workspace/nox/ops/draw")
import invoke_draw as D
Q = [("кот в космосе", "a cat in outer space"), ("красная машина на закате", "a red car at sunset"), ("дракон над морем", "a dragon above the sea"),
     ("замок зимой", "a castle in winter with snow"), ("робот с книгой", "a robot holding or reading a book")]
res = []
def vision(path, what):
    b = base64.b64encode(open(path, "rb").read()).decode()
    body = {"model": "x", "max_tokens": 80, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}},
                {"type": "text", "text": "Does this image clearly show: %s? Answer YES or NO first, then one short sentence describing what you see." % what}]}]}
    rq = urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(rq, timeout=240))["choices"][0]["message"]["content"].strip()
for ru, en in Q:
    t0 = time.time(); line = {"q": ru}
    try:
        dr = D.draw_request("нарисуй " + ru)
        r = D.local_generate(dr[1] if dr else ru, photographic=False)
        line.update(src=r.get("source"), s=round(r.get("seconds") or time.time() - t0, 1), path=r.get("path"))
        v = vision(r["path"], en); line["vision"] = v[:160]; line["match"] = v.upper().startswith("YES")
    except Exception as e:
        line["err"] = repr(e)[:200]
    print(json.dumps(line, ensure_ascii=False), flush=True)
print("DONE", flush=True)
