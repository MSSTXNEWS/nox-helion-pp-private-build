echo "C300: u_img2"
cd /workspace/nox/web/site/qa
/workspace/nox/venv/bin/python - <<'PYX'
from PIL import Image
import base64,io
im=Image.open('audit_desk_index.jpg');print(im.size)
im.thumbnail((900,563));b=io.BytesIO();im.save(b,'JPEG',quality=45);print('B64_BEGIN');s=base64.b64encode(b.getvalue()).decode()
for i in range(0,len(s),180): print('Z'+s[i:i+180]);print('B64_END')
PYX
cat /workspace/nox/agent/out/u_qab_prog.txt | cut -c1-300
