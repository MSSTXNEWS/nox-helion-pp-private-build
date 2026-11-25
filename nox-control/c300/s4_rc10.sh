echo S4RUN:s4_rc10
S=/workspace/nox/web/site/vendor
head -c 600 $S/paper-design-shaders/paper-design-shaders.iife.js | cut -c1-600; echo
grep -o "var NOX_[A-Za-z_0-9]*\|NOX_paper[A-Za-z_]*" $S/paper-design-shaders/paper-design-shaders.iife.js | head -3
grep -o "export{[^}]*}" $S/paper-design-shaders/paper-design-shaders.esm.js | tr ',' '\n' | grep -i "metaball\|ShaderMount\|defaultObjectSizing\|getShaderColor" | head
python3 - <<'P'
import re
t=open('/workspace/nox/web/site/vendor/paper-design-shaders/paper-design-shaders.esm.js').read()
i=t.find('uniform vec4 u_colorBack');print(len(t))
m=re.search(r'metaballsFragmentShader\s*=\s*`([^`]{0,1800})',t); print(m.group(1)[:1800] if m else 'nometa')
P
head -c 300 $S/tone/tone.iife.js; echo; grep -o "NOX_[A-Za-z]*" $S/tone/tone.iife.js | head -2
