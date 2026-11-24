S=/workspace/nox/web/site
sed -i 's#<meta http-equiv="refresh" content="4;url=chat.html">##' $S/resonance.html
sed -i 's#Через несколько секунд откроется чат\.#Откройте чат по кнопке ниже.#' $S/resonance.html
sed -n 37,44p $S/studio.html | cut -c1-500
grep -c "refresh" $S/resonance.html
