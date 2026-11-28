echo "K1: cr1 (read-only)"; N=/workspace/nox
echo "imgsvc :8500 = $(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8500/health) $(curl -s -m 5 http://127.0.0.1:8500/health | head -c 200)"
echo "--- imgsvc routes"; grep -nE "@(app|router)\.(get|post)|path ==|route\(|elif self.path|if self.path|do_(GET|POST)" $N/imgsvc/image_service.py | cut -c1-130 | head -30
echo "lines imgsvc=$(wc -l < $N/imgsvc/image_service.py) files: $(ls $N/imgsvc | head -20 | tr '\n' ' ')"
echo "--- draw tooling"; ls $N/ops/draw 2>/dev/null | head -20 | tr '\n' ' '; echo; grep -nE "def |15 с|уточн" $N/ops/draw/invoke_draw.py | cut -c1-120 | head -20
echo "--- VLM / CLIP on disk (names, sizes)"; find $N/models /workspace -maxdepth 5 \( -iname '*vl*' -o -iname '*clip*' -o -iname '*siglip*' -o -iname '*mmproj*' \) -not -path '*/venv/*' -not -path '*/node_modules/*' 2>/dev/null | head -20 | while read f; do echo "$(du -sm $f 2>/dev/null | cut -f1)MB ${f#/workspace/}"; done
echo "--- editor / asset_id / mask / inpaint"; grep -rlE "asset_id|inpaint|redraw|mask" $N/web $N/imgsvc $N/ops $N/mods $N/svc --include=*.py --include=*.js --include=*.jsx 2>/dev/null | grep -vE "node_modules|\.bak|venv" | head -15 | sed 's#/workspace/nox/##'
echo "--- three prohibitions filter"; grep -rlE "запрет|prohibit|nsfw|forbidden" $N/imgsvc $N/ops/draw $N/mods --include=*.py 2>/dev/null | head -8 | sed 's#/workspace/nox/##'; ls $N/models/images 2>/dev/null | head; 
echo "--- concerts: canon ch.12 file"; ls $N/state/canon* $N/canon* 2>/dev/null | head -5
echo "disk_G=$(df --output=avail -BG $N | tail -1 | tr -dc 0-9) vram_pct=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | awk -F', ' '{print int($1*100/$2)}')"
echo END
