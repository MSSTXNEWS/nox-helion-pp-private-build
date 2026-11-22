echo "== F4"
cd /root/nox/in_flash && gdown -q 1hX6kKQpJDxQcEl2a_cz7gTAha2QrbyNZ -O F.zip 2>&1 | tail -2; sha256sum F.zip | cut -c1-64; unzip -qo F.zip && ls | head
cd /root/nox/v5/nox_wow; ls; find . -name "README_V5.md" -o -name HANDOFF_V7.md -o -name run_all_tests.sh | head
R=$(find . -name README_V5.md | head -1); head -c 2500 $R
