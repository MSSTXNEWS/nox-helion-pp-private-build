echo "C300: k_v29dl"
D=/workspace/nox/web/v29src; mkdir -p $D; cd $D
cat > dl.sh <<'BG'
cd /workspace/nox/web/v29src; L=dl.log; echo "start $(date)" > $L
g(){ curl -sSL --retry 5 --retry-all-errors -o "$2" "https://drive.usercontent.google.com/download?id=$1&export=download&confirm=t" && echo "ok $2 $(stat -c %s "$2")" >> $L || echo "FAIL $2" >> $L; }
g 146NETh1Oo7mRSbU-pDRRmNGUEsrOI6YO V29_3_FROZEN.zip
g 1ZMC-zpKhcmvpCZv2icGFG4hOln3fR7OQ fw.part01
g 1Jcsj0jhn0WpUjecCyQA341eyfzJwHAdK fw.part02
g 1YgakwzmOHUw4ytzESjhHTB7IVIzDEJT1 fw.part03
g 1kmlL6rCNm0pkUY8OmXL7NMDiGRAhJgJf fw.part04
g 1qxYgM3WGs6m3ebsz_LSmkK634J1ShFS6 fw.part05
cat fw.part0? > FASTWOW.zip && echo "joined $(stat -c %s FASTWOW.zip)" >> $L
for z in V29_3_FROZEN FASTWOW; do mkdir -p $z && (cd $z && unzip -q -o ../$z.zip) && echo "unz $z $(find $z -type f | wc -l)" >> $L || echo "UNZFAIL $z $(file ../$z.zip)" >> $L; done
echo DONE >> $L
BG
setsid -f bash dl.sh </dev/null >/dev/null 2>&1
sleep 200; cat dl.log; df -h /workspace | tail -1
