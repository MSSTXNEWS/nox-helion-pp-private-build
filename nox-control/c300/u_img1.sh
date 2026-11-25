echo "C300: u_img1"
cd /workspace/nox/web/site/qa
/workspace/nox/venv/bin/python - <<'PYX'
from PIL import Image
import base64,io
im=Image.open('audit_desk_index.jpg');print(im.size)
im.thumbnail((1280,800));b=io.BytesIO();im.save(b,'JPEG',quality=60);print('B64_BEGIN');print(base64.b64encode(b.getvalue()).decode());print('B64_END')
PYX
cat /workspace/nox/agent/out/u_qab_prog.txt | cut -c1-300
