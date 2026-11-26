echo "C300: tr_recon2"
cd /workspace/nox
red(){ sed -E 's/(sk-|ghp_|hf_|AIza|xox[a-z]-)[A-Za-z0-9_-]{8,}/\1REDACTED/g; s/((TOKEN|KEY|SECRET|PASS)[A-Z_]*=)[^ "]+/\1REDACTED/g'; }
for f in agent/autotrain/autotrain.sh ops/dpo/gates_only.py ops/dpo/ext_eval.py ops/dpo/run_dpo.sh ops/dpo/chain6.sh ops/dpo/dpo_report.json ops/dpo/gates_ebf02c04001131ac.json; do echo "######## $f"; red < $f; done
echo "######## head ext_cases"; head -c 2500 ops/dpo/ext_cases.py | red
echo END
