echo "C300: q_probe1"
which git; git --version
for f in /root/.git-credentials /root/.config/gh/hosts.yml; do [ -f $f ] && echo "HAS $f"; done
env | grep -c -i "github_pat\|GH_TOKEN\|GITHUB_TOKEN" 
grep -rl "github_pat_" /workspace/nox/state/secrets /root/.config 2>/dev/null | head -5
ls /workspace/nox/state/secrets 2>/dev/null | head -20
cd /tmp && rm -rf qprobe && timeout 40 git clone -q --depth 1 https://github.com/MSSTXNEWS/nox-helion-pp-private-build.git qprobe && echo CLONE_OK; rm -rf qprobe
nproc; uptime
