echo "K1: l2_liv_recon1"
sed -n 27,70p /workspace/nox/svc/living/living_svc.py | cut -c1-230
sed -n 138,212p /workspace/nox/svc/living/living_svc.py | cut -c1-260
sed -n 234,246p /workspace/nox/svc/living/living_svc.py | cut -c1-200
supervisorctl status | grep -i living; grep -n living /workspace/nox/svc/start_extra.sh | head -3 | cut -c1-200
