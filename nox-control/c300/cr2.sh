echo "K1: cr2 (read-only code view)"; N=/workspace/nox
sed -n 33,64p $N/ops/draw/invoke_draw.py | cut -c1-200
echo ----- check_prompt/_gate; sed -n 114,123p $N/ops/draw/invoke_draw.py | cut -c1-220; sed -n 145,160p $N/ops/draw/invoke_draw.py | cut -c1-200
echo ----- imgsvc POST; sed -n 300,332p $N/imgsvc/image_service.py | cut -c1-220
echo ----- safety_check heads; grep -nE "^def |^[A-Z_]+ *=|запрет|PROHIB|BAN|three|три" $N/ops/draw/safety_check.py | cut -c1-160 | head -30
echo ----- editor front; grep -noE "asset_id|inpaint|mask|before.after|redraw" $N/web/pkg/webroot/nox-dz-creative.js | sort | uniq -c | head; ls $N/web/pkg/webroot | grep -iE "editor|redakt|creative|studio" | head
echo ----- assets store; ls $N/state | grep -iE "asset|image|draw|creative" | head; ls $N/state/assets 2>/dev/null | head -3
echo END
