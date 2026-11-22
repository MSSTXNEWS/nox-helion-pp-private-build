#!/bin/bash
# c170: библиотеки для богатых ответов чата и страниц (marked, DOMPurify, KaTeX, Mermaid, Plyr) -> $NOX_VENDOR/nox-lib/<имя>/ (npm, версии закреплены). Идемпотентно, ничего не удаляется.
V=${NOX_VENDOR:-/root/nox/web/vendor}; L=$V/nox-lib; T=${TMPDIR:-/tmp}/nox170npm
mkdir -p "$L"; need=0
for f in marked/marked.min.js dompurify/purify.min.js katex/katex.min.js katex/katex.min.css katex/auto-render.min.js mermaid/mermaid.min.js plyr/plyr.min.js plyr/plyr.css plyr/plyr.svg; do [ -s "$L/$f" ] || need=1; done
if [ $need = 1 ]; then
  rm -rf "$T"; mkdir -p "$T"; cd "$T" || exit 1; npm init -y >/dev/null 2>&1
  timeout 300 npm i --no-audit --no-fund --silent marked@12.0.2 dompurify@3.1.6 katex@0.16.11 mermaid@10.9.1 plyr@3.7.8 2>&1 | tail -3
  N=$T/node_modules
  mkdir -p $L/marked $L/dompurify $L/katex/fonts $L/mermaid $L/plyr
  cp $N/marked/marked.min.js $N/marked/LICENSE.md $L/marked/ 2>/dev/null
  cp $N/dompurify/dist/purify.min.js $N/dompurify/LICENSE $L/dompurify/ 2>/dev/null
  cp $N/katex/dist/katex.min.js $N/katex/dist/katex.min.css $N/katex/dist/contrib/auto-render.min.js $N/katex/LICENSE $L/katex/ 2>/dev/null
  cp $N/katex/dist/fonts/*.woff2 $L/katex/fonts/ 2>/dev/null
  cp $N/mermaid/dist/mermaid.min.js $N/mermaid/LICENSE $L/mermaid/ 2>/dev/null
  cp $N/plyr/dist/plyr.min.js $N/plyr/dist/plyr.css $N/plyr/dist/plyr.svg $N/plyr/LICENSE.md $L/plyr/ 2>/dev/null
  cd /; rm -rf "$T"
fi
echo "nox-lib: $(cd $L && for f in marked/marked.min.js dompurify/purify.min.js katex/katex.min.js katex/auto-render.min.js mermaid/mermaid.min.js plyr/plyr.min.js plyr/plyr.svg; do [ -s $f ] && echo -n "$f=ok " || echo -n "$f=НЕТ "; done)"; du -sh $L | cut -f1
