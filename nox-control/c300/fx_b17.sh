P=/workspace/nox/web/pkg/server; S=/workspace/nox/web/site
awk '/    def _memory\(/{f=1} f{print substr($0,1,220)} /def _proxy/{if(f)exit}' $P/web_server.py | head -30
grep -n "props" $S/models.html $S/nox-p-*.js 2>/dev/null | cut -c1-260 | head -5
grep -n "def _glm_compat" $P/web_server.py
date; pgrep -af qa_ctl | wc -l; tail -2 $S/qa/history.log
