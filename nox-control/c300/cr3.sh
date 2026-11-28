echo "K1: cr3 (read-only code view)"; N=/workspace/nox
grep -nE "def handle_generate|def _check|check_prompt|_MINOR|_DEEPFAKE|_ILLEGAL|forbid|prohib|def _safety|safety|text_enc|--clip|t5" $N/imgsvc/image_service.py | cut -c1-170 | head -30
echo --- order in handle_generate; L=$(grep -n "def handle_generate" $N/imgsvc/image_service.py | cut -d: -f1); sed -n "${L},$((L+45))p" $N/imgsvc/image_service.py | cut -c1-190
echo --- invoke_draw flow; grep -nE "check_prompt\(|_flux\(|_local\(|_gate\(|def draw\(|def run|asset|out_path|png" $N/ops/draw/invoke_draw.py | cut -c1-150 | head -24
echo --- editor api calls; grep -noE "fetch\([^)]{0,80}\)|/api/[a-z_/-]+" $N/web/pkg/webroot/nox-editor-s1.js | sort -u | head -20
grep -rnoE "/api/(editor|asset|draw|img)[a-z_/-]*" $N/web/pkg/server/*.py 2>/dev/null | sort -u | head -15
echo --- images dir; ls $N/state/images 2>/dev/null | wc -l; ls -d $N/imgsvc/out $N/state/img* 2>/dev/null
echo END
