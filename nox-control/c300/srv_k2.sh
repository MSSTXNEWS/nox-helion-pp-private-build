echo "C300: srv_k2"
cd /workspace/nox
grep -rIl "worms/night\|def .*worm\|hf_scan\|scan_hf" --include=*.py agent ops 2>/dev/null | head
echo "== tools_gw"; supervisorctl tail nox_tools_gateway stderr 2>&1 | tail -8
for p in 8141 8142 8143; do ss -ltn | grep ":$p " | head -1; done
echo "== net"
curl -s -m 10 -o /dev/null -w "hf %{http_code}\n" "https://huggingface.co/api/models?sort=lastModified&limit=2"
curl -s -m 10 -o /dev/null -w "gh %{http_code}\n" "https://api.github.com/search/repositories?q=lora+moe&per_page=1"
curl -s -m 10 -o /dev/null -w "rss %{http_code}\n" "https://hnrss.org/frontpage"
curl -s -m 10 -o /dev/null -w "arxiv %{http_code}\n" "http://export.arxiv.org/rss/cs.LG"
env | grep -i proxy | sed 's/=.*/=SET/'
