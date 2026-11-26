/* NOX photo-dc (WEB): диалог Фотостудии на готовом Deep Chat. Тонкий адаптер к прежней логике nox-photo.js (скрытые #cIn/#cGo/#cLog и переключатель «NOX видит холст» остаются источником правды). Откат: ?pdc=0 */
(function(){
if(/[?&]pdc=0/.test(location.search))return;
var box=document.querySelector('.ps-chat'),cin=document.getElementById('cIn'),go=document.getElementById('cGo'),log=document.getElementById('cLog');
if(!box||!cin||!go||!log)return;
var st=document.createElement('style');st.textContent='.ps-chat #cLog,.ps-chat .ps-row{display:none!important}.ps-chat deep-chat{display:block;width:100%!important;height:340px!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:14px!important;background:transparent!important}.ps-chat .ps-see{margin:8px 0}';document.head.appendChild(st);
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function mount(){
 var dc=document.createElement('deep-chat');dc.setAttribute('aria-label','Диалог с NOX');
 box.insertBefore(dc,log);
 dc.introMessage={text:'Я в Фотостудии. Скажи, что нарисовать, или включи «NOX видит холст» — подскажу по фото.'};
 dc.messageStyles={default:{shared:{bubble:{borderRadius:'12px',padding:'8px 12px',fontSize:'15px',lineHeight:'1.55',maxWidth:'94%'}},user:{bubble:{backgroundColor:'#2a2c30',color:'#edeef0'}},ai:{bubble:{backgroundColor:'transparent',color:'#edeef0'}}}};
 dc.textInput={placeholder:{text:'«Нарисуй уютный дом в горах ночью» или «что улучшить на фото?»'},styles:{container:{backgroundColor:'rgba(255,255,255,.05)',border:'1px solid rgba(255,255,255,.12)',borderRadius:'12px'},text:{color:'#edeef0',fontSize:'15px'}}};
 dc.connect={handler:function(body,signals){
  var m=body.messages||[],q=(m[m.length-1]||{}).text||'';if(!q.trim()){signals.onResponse({error:'Пустое сообщение'});return}
  var before=log.children.length;cin.value=q;go.click();
  var t=0,iv=setInterval(function(){t++;var nodes=[].slice.call(log.children).slice(before+1);
   if(!go.disabled&&t>2||t>600){clearInterval(iv);
    var html='',txt=[];nodes.forEach(function(n){var im=n.querySelector&&n.querySelector('img');var tx=(n.firstChild&&n.firstChild.nodeType===3?n.firstChild.textContent:n.textContent)||'';if(tx.trim()&&tx.trim()!=='…')html+='<div>'+esc(tx)+'</div>';if(im)html+='<img src="'+esc(im.src)+'" alt="Сгенерированная картинка" style="max-width:100%;border-radius:10px;margin-top:6px;cursor:pointer" data-nxp="1">'});
    if(!html){var last=log.lastElementChild;html='<div>'+esc((last&&last.textContent)||'NOX не ответил')+'</div>'}
    signals.onResponse({html:html})}},400)}};
 var n=0,iv=setInterval(function(){var r=dc.shadowRoot;if(r){r.querySelectorAll('.input-button:not([aria-label])').forEach(function(b){b.setAttribute('aria-label','Отправить')});r.querySelectorAll('[role=button]:not([aria-label])').forEach(function(b){b.setAttribute('aria-label','Отправить')})}if(++n>40)clearInterval(iv)},500);
 dc.requestBodyLimits={maxMessages:1};
 var autoload=function(){};
}
function boot(){customElements.whenDefined('deep-chat').then(mount)}
if(customElements.get('deep-chat'))mount();else{var s=document.createElement('script');s.src='./vendor/deep-chat/deep-chat.iife.js';s.onload=boot;s.onerror=function(){};document.head.appendChild(s)}
})();
