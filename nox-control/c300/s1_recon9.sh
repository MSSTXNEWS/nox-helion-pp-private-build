cd /workspace/nox/web/site
cat nox-home-x.css | cut -c1-700
echo ==QA; sed -n 5p nox-home-x.js | cut -c1-1500
echo ==PHOME; wc -c nox-p-home.js; grep -n "innerHTML\|className\|class=" nox-p-home.js | cut -c1-330 | head -30
echo ==PAGES; grep -n "\.grid\|\.card\|\.c4\|\.led\|\.ph\b\|\.ph{\|\.wrap\|\.tag\|\.page{" nox-pages.css | cut -c1-260 | head -30
