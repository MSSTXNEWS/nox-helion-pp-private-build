n=$1; cd /home/claude/mrepo/nox-control/c300; sed "s/NAME/$n/" poll.tpl > $n.sh; git add -A; git commit -qm $n -q; git pull --rebase -q; git push -q 2>&1|tail -1
gh api -X POST repos/MSSTXNEWS/nox-helion-pp-private-build/actions/workflows/nox-c300.yml/dispatches -f ref=main -f inputs[script]=$n.sh 2>&1|tail -2
sleep ${2:-100}
for id in $(gh run list --workflow nox-c300.yml -L 6 --json databaseId -q .[].databaseId); do o=$(gh run view $id --log 2>&1); echo "$o" | grep -q "C300: $n$" && echo "$o" | sed -n "/C300: $n\$/,/Post Run/p" | cut -d' ' -f4- | cut -c30-300; done
