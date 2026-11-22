echo "== F3"
cd /root/nox/in_v5; ls | wc -l
sha256sum NOX_V7_BRAIN_OPT_20261122_v5.zip | cut -c1-64
mkdir -p /root/nox/v5 && cd /root/nox/v5 && unzip -qo ../in_v5/NOX_V7_BRAIN_OPT_20261122_v5.zip && ls | head -30
cd /root/nox/in_v5 && bash JOIN_WEB_V5.sh 2>&1 | tail -3; ls -la *.zip | awk '{print $5,$9}'
# второй пакет
mkdir -p /root/nox/in_flash && cd /root/nox/in_flash && gdown --id 1hX6kKQpJDxQcEl2a_cz7gTAha2QrbyNZ -q -O NOX_S1_FLASH_OPTIM_EXEC_FULL_20261122.zip 2>&1 | tail -2
sha256sum *.zip | cut -c1-64; ls -l | awk '{print $5,$9}'
