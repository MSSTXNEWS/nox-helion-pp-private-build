echo "C300: rv_s1"
cd /workspace/nox/state/rv
for f in chatfn_text_1440 chatfn_draw_1440 chatfn_draw_390; do echo "IMG $f"; /workspace/nox/venv/bin/python -c "
from PIL import Image;import io,base64
im=Image.open('$f.jpg');im.thumbnail((700,700));b=io.BytesIO();im.save(b,'JPEG',quality=60);print(base64.b64encode(b.getvalue()).decode())"; done
