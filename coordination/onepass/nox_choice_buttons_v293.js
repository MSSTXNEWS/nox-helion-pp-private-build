/* NOX WEB V29.3: replace 13 visible legacy dropdowns with live metallic
   button groups. Original select remains as the canonical form/data binding;
   no fake handlers, no external dependencies, no backend or memory changes. */
(() => {
  'use strict';
  const STYLE_ID='nox-v293-choice-buttons-style';
  const SELECTOR='select.nx-in';
  function styles(){
    if(document.getElementById(STYLE_ID))return;
    const style=document.createElement('style');
    style.id=STYLE_ID;
    style.textContent=[
      '.nox-v293-native-select{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important;overflow:hidden!important;clip-path:inset(50%)!important;}',
      '.nox-v293-choice-row{display:flex;align-items:stretch;flex-wrap:wrap;gap:8px;max-width:100%;padding:5px 0 9px;}',
      '.nox-v293-choice-button{appearance:none;border:1px solid rgba(198,159,92,.6);background:linear-gradient(135deg,#27272a 0%,#111113 48%,#2b2620 100%);color:#f1e3c9;font-weight:600;font-size:12px;line-height:1.4;font-family:inherit;letter-spacing:.025em;text-shadow:0 1px 1px #000;box-shadow:inset 0 1px 0 rgba(255,230,172,.12),0 3px 8px rgba(0,0,0,.25);border-radius:8px;min-height:36px;padding:9px 12px;max-width:100%;white-space:normal;overflow-wrap:anywhere;cursor:pointer;transition:filter .13s ease,transform .13s ease,border-color .13s ease;}',
      '.nox-v293-choice-button:hover:not(:disabled){border-color:#eec989;filter:brightness(1.17);transform:translateY(-1px);}',
      '.nox-v293-choice-button[aria-pressed="true"]{border-color:#e7ba6e;background:linear-gradient(155deg,#62471e 0%,#2c2418 48%,#392d1a 100%);box-shadow:inset 0 0 0 1px rgba(255,220,141,.23),0 0 12px rgba(224,160,54,.16);color:#fff5da;}',
      '.nox-v293-choice-button:focus-visible{outline:2px solid #f7d38e;outline-offset:2px;}',
      '.nox-v293-choice-button:disabled{opacity:.4;cursor:not-allowed;}',
      '.nox-v293-choice-empty{font-size:12px;color:#c4b49b;font-style:italic;padding:8px 0;}',
      '@media(prefers-reduced-motion:reduce){.nox-v293-choice-button{transition:none!important;transform:none!important;}}'
    ].join('\n');
    document.head.appendChild(style);
  }
  function labelFor(select){
    const id=select.id;
    const own=id?Array.from(document.querySelectorAll('label[for]')).find(el=>el.htmlFor===id):null;
    const text=(select.title||(own&&own.textContent)||select.getAttribute('aria-label')||id||'Выбор').trim();
    return text.slice(0,90);
  }
  function replaceDropdown(select){
    if(select.dataset.noxChoiceButtons==='installed')return;
    select.dataset.noxChoiceButtons='installed';
    styles();
    const row=document.createElement('div');
    row.className='nox-v293-choice-row';
    row.setAttribute('role','group');
    row.setAttribute('aria-label',labelFor(select));
    if(select.id)row.dataset.targetSelect=select.id;
    select.insertAdjacentElement('afterend',row);
    select.classList.add('nox-v293-native-select');
    select.setAttribute('aria-hidden','true');
    select.tabIndex=-1;
    let frame=0;
    function sync(){
      const buttons=row.querySelectorAll('button[data-option-index]');
      buttons.forEach(button=>{
        const option=select.options[Number(button.dataset.optionIndex)];
        const chosen=Boolean(option&&option.selected);
        button.setAttribute('aria-pressed',String(chosen));
        button.disabled=Boolean(select.disabled||!option||option.disabled);
      });
    }
    function render(){
      frame=0;
      const fragment=document.createDocumentFragment();
      Array.from(select.options).forEach((option,index)=>{
        const button=document.createElement('button');
        button.type='button';
        button.className='nox-v293-choice-button';
        button.dataset.optionIndex=String(index);
        button.textContent=(option.textContent||option.label||option.value||'Вариант').trim();
        button.title=button.textContent;
        button.setAttribute('aria-pressed',String(option.selected));
        button.disabled=Boolean(select.disabled||option.disabled);
        button.addEventListener('click',()=>{
          if(select.disabled||option.disabled)return;
          if(select.multiple){
            option.selected=!option.selected;
          }else{
            select.selectedIndex=index;
          }
          select.dispatchEvent(new Event('input',{bubbles:true}));
          select.dispatchEvent(new Event('change',{bubbles:true}));
          sync();
        });
        fragment.appendChild(button);
      });
      if(!select.options.length){
        const empty=document.createElement('span');
        empty.className='nox-v293-choice-empty';
        empty.textContent='Варианты загружаются из действующего источника';
        fragment.appendChild(empty);
      }
      row.replaceChildren(fragment);
      sync();
    }
    function schedule(){
      if(frame)return;
      frame=window.requestAnimationFrame(render);
    }
    const observer=new MutationObserver(schedule);
    observer.observe(select,{childList:true,subtree:true,attributes:true,attributeFilter:['selected','disabled','value','label'],characterData:true});
    select.addEventListener('change',sync);
    select.addEventListener('input',sync);
    render();
    // Keep observer attached to the existing control for future source updates.
    select._noxV293ChoiceObserver=observer;
  }
  function init(){
    document.querySelectorAll(SELECTOR).forEach(replaceDropdown);
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',init,{once:true});
  }else{
    init();
  }
})();
