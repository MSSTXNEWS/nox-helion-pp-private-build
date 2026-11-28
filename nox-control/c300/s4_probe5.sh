N=/workspace/nox
echo "S4P5 $(date +%F_%H:%M)"
cd $N/brain/GROW/upgrade && python3 -I - <<'PY'
import sys; sys.path.insert(0,"/workspace/nox/brain/GROW/upgrade"); import soul_recognition as SR
for s in SR.SITUATIONS:
    if s["id"] in ("inj_system_dump","false_memory","loyal_stranger_pass","inj_summary_ad","inj_translate_data","honesty_unknown","mem_fake_promise","loyal_stranger_report"):
        print(s["id"],"|",s["prompt"][:400].replace("\n"," / "),"|ANY:",s["must_any"],"|NOT:",s["must_not"],"|MAX",s["max_words"])
PY
