mkdir -p /workspace/nox/svc/data
cat > /workspace/nox/svc/install.sh <<'EOF'
#!/bin/bash
# установка сервисов NOX (без Docker): бинарники в /workspace/nox/svc/<имя>, данные в /workspace/nox/svc/data/<имя>
S=/workspace/nox/svc; D=$S/data; REG=/workspace/nox/web/pkg/server/svc_registry.json
cd $S
gh_asset(){ # repo pattern
  curl -fsSL "https://api.github.com/repos/$1/releases/latest" | python3 -c "
import json,sys,re
d=json.load(sys.stdin)
for a in d['assets']:
    if re.search(sys.argv[1],a['name']): print(a['browser_download_url']); break" "$2"; }
reg(){ python3 - "$@" <<'PY'
import json,sys
p='/workspace/nox/web/pkg/server/svc_registry.json'; d=json.load(open(p))
n,port,mode,title=sys.argv[1:5]; e={'port':int(port),'mode':mode,'title':title}
for kv in sys.argv[5:]:
    k,v=kv.split('=',1); e[k]=json.loads(v)
d[n]=e; json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
PY
}
# --- Filebrowser
if [ ! -x filebrowser/filebrowser ]; then mkdir -p filebrowser $D/filebrowser /workspace/nox/dl_files; U=$(gh_asset filebrowser/filebrowser '^linux-amd64-filebrowser\.tar\.gz$'); echo FB $U; curl -fsSL "$U" | tar xz -C filebrowser; fi
if [ ! -f $D/filebrowser/fb.db ]; then ./filebrowser/filebrowser config init -d $D/filebrowser/fb.db -a 127.0.0.1 -p 8097 -b /svc/filebrowser -r /workspace/nox/dl_files >/dev/null; ./filebrowser/filebrowser config set -d $D/filebrowser/fb.db --auth.method=noauth >/dev/null; ./filebrowser/filebrowser users add admin "$(head -c 12 /dev/urandom | base64 | tr -d '/+=')" --perm.admin -d $D/filebrowser/fb.db >/dev/null 2>&1; fi
reg filebrowser 8097 base "Filebrowser" 'note="Корень: /workspace/nox/dl_files, без входа"'
# --- Navidrome
if [ ! -x navidrome/navidrome ]; then mkdir -p navidrome $D/navidrome /workspace/nox/music_lib; U=$(gh_asset navidrome/navidrome '_linux_amd64\.tar\.gz$'); echo ND $U; curl -fsSL "$U" | tar xz -C navidrome; fi
reg navidrome 4533 base "Navidrome" 'note="Музыка: /workspace/nox/music_lib"'
# --- ntfy
if [ ! -x ntfy/ntfy ]; then mkdir -p ntfy $D/ntfy; U=$(gh_asset binwiederhier/ntfy '_linux_amd64\.tar\.gz$'); echo NTFY $U; curl -fsSL "$U" | tar xz -C ntfy --strip-components=1; fi
reg ntfy 2586 strip "ntfy" 'ui=false' 'note="API уведомлений: POST /svc/ntfy/<тема>"'
# --- Jellyfin
if [ ! -x jellyfin/jellyfin ]; then mkdir -p jellyfin $D/jellyfin/config; curl -s https://repo.jellyfin.org/files/server/linux/latest-stable/amd64/ | grep -o 'jellyfin_[0-9.]*-amd64\.tar\.gz"' | head -1 | tr -d '"' > /tmp/jf.name; N=$(cat /tmp/jf.name); echo JF $N; curl -fsSL "https://repo.jellyfin.org/files/server/linux/latest-stable/amd64/$N" | tar xz -C jellyfin --strip-components=1; fi
cat > $D/jellyfin/config/network.xml <<X
<?xml version="1.0" encoding="utf-8"?>
<NetworkConfiguration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema"><BaseUrl>/svc/jellyfin</BaseUrl><EnableHttps>false</EnableHttps><HttpServerPortNumber>8096</HttpServerPortNumber><AutoDiscovery>false</AutoDiscovery><EnableUPnP>false</EnableUPnP><LocalNetworkAddresses><string>127.0.0.1</string></LocalNetworkAddresses></NetworkConfiguration>
X
reg jellyfin 8096 base "Jellyfin" 'note="Первый запуск: мастер настройки в рамке"'
# --- FreshRSS (php)
if ! command -v php >/dev/null; then DEBIAN_FRONTEND=noninteractive apt-get install -y -qq php-cli php-sqlite3 php-xml php-mbstring php-curl php-zip php-intl php-gd >/dev/null 2>&1; fi
php -v | head -1
if [ ! -d freshrss/p ]; then mkdir -p freshrss; U=$(curl -fsSL https://api.github.com/repos/FreshRSS/FreshRSS/releases/latest | python3 -c "import json,sys;print(json.load(sys.stdin)['zipball_url'])"); curl -fsSL "$U" -o /tmp/frss.zip && python3 -c "
import zipfile,os,shutil
z=zipfile.ZipFile('/tmp/frss.zip');top=z.namelist()[0].split('/')[0];z.extractall('/tmp/frss_x');
import glob;src=glob.glob('/tmp/frss_x/*')[0];
for f in os.listdir(src): shutil.move(os.path.join(src,f),'/workspace/nox/svc/freshrss/'+f)
"; rm -rf /tmp/frss_x /tmp/frss.zip; fi
reg freshrss 8098 strip "FreshRSS" 'note="Новости: RSS-агрегатор (PHP, SQLite)"'
echo INSTALL_DONE
EOF
cat > /workspace/nox/svc/start_all.sh <<'EOF'
#!/bin/bash
# запуск сервисов NOX (идемпотентно); все слушают 127.0.0.1
S=/workspace/nox/svc; D=$S/data; L=$S/logs; mkdir -p $L
up(){ (echo > /dev/tcp/127.0.0.1/$1) 2>/dev/null; }
up 8097 || { [ -x $S/filebrowser/filebrowser ] && nohup setsid $S/filebrowser/filebrowser -d $D/filebrowser/fb.db >$L/filebrowser.log 2>&1 & }
up 4533 || { [ -x $S/navidrome/navidrome ] && ND_ADDRESS=127.0.0.1 ND_PORT=4533 ND_BASEURL=/svc/navidrome ND_MUSICFOLDER=/workspace/nox/music_lib ND_DATAFOLDER=$D/navidrome ND_LOGLEVEL=warn ND_ENABLEINSIGHTSCOLLECTOR=false nohup setsid $S/navidrome/navidrome >$L/navidrome.log 2>&1 & }
up 2586 || { [ -x $S/ntfy/ntfy ] && nohup setsid $S/ntfy/ntfy serve --listen-http 127.0.0.1:2586 --cache-file $D/ntfy/cache.db --base-url http://localhost:8091/svc/ntfy >$L/ntfy.log 2>&1 & }
up 8096 || { [ -x $S/jellyfin/jellyfin ] && DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 nohup setsid $S/jellyfin/jellyfin --datadir $D/jellyfin --configdir $D/jellyfin/config --cachedir $D/jellyfin/cache --logdir $D/jellyfin/log --ffmpeg /usr/bin/ffmpeg >$L/jellyfin.log 2>&1 & }
up 8098 || { [ -d $S/freshrss/p ] && command -v php >/dev/null && nohup setsid php -S 127.0.0.1:8098 -t $S/freshrss/p >$L/freshrss.log 2>&1 & }
[ -x $S/start_extra.sh ] && bash $S/start_extra.sh
exit 0
EOF
chmod +x /workspace/nox/svc/*.sh
grep -q svc/start_all.sh /root/onstart.sh || echo '(sleep 40; bash /workspace/nox/svc/start_all.sh >> /workspace/nox/svc/logs/start.log 2>&1) &' >> /root/onstart.sh
nohup setsid bash -c 'bash /workspace/nox/svc/install.sh > /workspace/nox/svc/install.log 2>&1; bash /workspace/nox/svc/start_all.sh' >/dev/null 2>&1 &
sleep 100; tail -20 /workspace/nox/svc/install.log; df -h /workspace | tail -1
