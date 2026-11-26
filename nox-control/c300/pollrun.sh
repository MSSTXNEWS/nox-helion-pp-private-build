n=$1; cd /home/claude/mrepo/nox-control/c300; sed "s/NAME/$n/" poll.tpl > $n.sh; git add -A; git commit -qm $n -q; git pull --rebase -q; git push -q 2>&1|tail -1
gh api -X POST repos/MSSTXNEWS/nox-helion-pp-private-build/actions/workflows/nox-c300.yml/dispatches -f ref=main -f inputs[script]=$n.sh 2>&1|tail -2
