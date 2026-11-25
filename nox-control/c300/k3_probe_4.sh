echo "C300: k3_probe_4"
S=/workspace/nox/web/site; cd $S
grep -n "localStorage\|const load\|function load" nox-fin-s1.js | head -4 | cut -c1-260
sed -n 1,30p nox-cmd.js | cut -c1-220
grep -n "NOXcmdRegistry\|window.NOXcmd\b" nox-cmd.js | head; grep -o "reg\.[a-zA-Z]*" nox-cmd.js | sort -u | tr '\n' ' '
grep -rn "NOXcmd.register\|NOXcmdRegister" nox-*.js | head -3 | cut -c1-240
grep -n "chat.send" nox-cmd.js nox-actions.js | head -3 | cut -c1-260
exit 0
