echo "C300: ch_dc6"
N=/workspace/nox; head -c 2500 $N/agent/out/dc_ui.log | cut -c1-260; ls -t $N/agent/out/ui_sc | head -5; ls $N/agent/out/ui_sc | grep -i chat | head
