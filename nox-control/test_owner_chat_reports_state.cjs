'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');

test('real report polling preserves manual close and announces only changed counters',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'owner-chat-ui.js'),'utf8');
  const creation=source.slice(source.indexOf('    const reports='),source.indexOf('    const reportStyle='));
  const polling=source.slice(source.indexOf('    let eventCursor='),source.indexOf('    void refreshEvents();'));
  assert.ok(creation.length>100&&polling.length>500);
  class Element{
    constructor(tag,text){this.tag=tag;this.value=text||'';this.writes=0;this.children=[];this.dataset={};this.attrs={};this.open=false;}
    set textContent(value){this.value=value;this.writes++;}get textContent(){return this.value;}
    setAttribute(key,value){this.attrs[key]=value;}append(...items){this.children.push(...items);}
    get childElementCount(){return this.children.length;}
    querySelector(selector){const value=selector.match(/data-event-sequence="([0-9]+)"/)[1];return this.children.find(item=>item.dataset.eventSequence===value)||null;}
  }
  const batches=[1,2,null,null];let cursor=0;
  const context={E:(tag,text)=>new Element(tag,text),statusStack:new Element('section'),document:{hidden:false},
    localStorage:{getItem:()=>null,setItem:()=>{}},Date,Number,String,
    api:async(url)=>{assert.match(url,/^\/api\/ui\/events\?limit=20/);const next=batches.shift();if(next)cursor=next;
      return{schema:'NOX_OWNER_EVENTS_V1',next_cursor:cursor,events:next?[{sequence:next,title:'Public QA',message:'Event',created_at:1}]:[]};}};
  const ui=vm.runInNewContext('(()=>{'+creation+polling+';return {reports,reportTitle,reportList,refreshEvents};})()',context);
  assert.equal(ui.reports.open,true);assert.equal(ui.reportTitle.attrs['aria-live'],'polite');
  await ui.refreshEvents();assert.equal(ui.reportList.childElementCount,1);
  ui.reports.open=false;
  await ui.refreshEvents();assert.equal(ui.reports.open,false);assert.equal(ui.reportList.childElementCount,2);
  assert.match(ui.reportTitle.textContent,/2$/);const writes=ui.reportTitle.writes;
  await ui.refreshEvents();assert.equal(ui.reports.open,false);assert.equal(ui.reportTitle.writes,writes);
  ui.reports.open=true;await ui.refreshEvents();assert.equal(ui.reports.open,true);
});
