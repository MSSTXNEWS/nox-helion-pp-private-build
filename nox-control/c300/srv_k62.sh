echo "C300: srv_k62"
cd /workspace/nox/brain/SLP
wc -l fidelity_cases.py fidelity_test.py
sed -n '1,40p' fidelity_cases.py | cut -c1-260
grep -n "just_model\|injection\|false_memory\|flattery" fidelity_cases.py | head -20 | cut -c1-200
sed -n '1,60p' fidelity_test.py | cut -c1-220
