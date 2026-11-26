echo "C300: ch_r4"
P=/workspace/nox/svc/pipeline/pipeline_svc.py; grep -n "^def \|^import\|^[A-Z_]* *=" $P | head -70
echo ----; sed -n "$(grep -n '^def models' $P | cut -d: -f1),+40p" $P | cut -c1-260
echo ----; sed -n "$(grep -n '^def advise' $P | cut -d: -f1),+45p" $P | cut -c1-260
