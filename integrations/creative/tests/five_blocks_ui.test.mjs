// Validates the actual CS5 add-on in the ORIGINAL NOX Creative DOM (no root HOME/MENU).
// Run: node --test integrations/creative/tests/five_blocks_ui.test.mjs
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {execFileSync} from 'node:child_process';

const source = readFileSync(new URL('../web/five_blocks.js', import.meta.url), 'utf8');

test('Creative add-on is ordered after original Studio and does not change native menu entry', () => {
  const html = readFileSync(new URL('../web/studio.html', import.meta.url), 'utf8');
  const expected = '34032ba9cb41bc3d71afcdbe57f690e15fd76755';
  // Windows Git may use CRLF in the checkout; compare the CANONICAL Git blob.
  const hash = execFileSync('git', [
    'rev-parse', 'HEAD:integrations/creative/web/entry.js'
  ], {encoding:'utf8'}).trim();
  assert.equal(hash, expected, 'original Creative launcher Git blob must remain byte-identical');
  const first = html.indexOf('<script src="studio.js"></script>');
  const addon = html.indexOf('<script src="five_blocks.js"></script>');
  const last = html.indexOf('<script src="persona-media.js"></script>');
  assert.ok(first >= 0 && addon > first && last > addon,
    'CS5 must reuse the original Studio runtime, never replace HOME/MENU');
});

function mount() {
  const ids = new Map(), calls = [], navEvents = [], actions = [];
  class Element {
    constructor(tag='div') {
      this.tag=tag;this.dataset={};this.children=[];this.handlers={};this.value='';
      this.textContent='';this.innerHTML='';this.style={};
    }
    addEventListener(event, fn) {this.handlers[event]=fn;}
    setAttribute(name, value) {this[name] = String(value);}
    appendChild(node) {
      this.children.push(node);
      for (const match of node.innerHTML.matchAll(/id="([^"]+)"/g)) {
        if (!ids.has(match[1])) ids.set(match[1], new Element());
      }
      if (ids.has('cs5-block')) ids.get('cs5-block').value='B01';
      if (ids.has('cs5-project')) ids.get('cs5-project').value='creative01';
    }
    append(...nodes) {this.children.push(...nodes);}
    replaceChildren(){this.children=[];}
    focus(){}
    click(){return this.handlers.click?.();}
  }
  const nav=new Element('nav'), main=new Element('main');
  let activeScreen = 'create';
  const document={
    getElementById: name=>ids.get(name)||null,
    querySelector: selector=>selector==='nav.nav'?nav:
      selector==='.layout main.content'?main:
      selector==='.screen.active'?{id:'screen-'+activeScreen}:null,
    createElement: tag=>new Element(tag),
  };
  for (const name of ['project','prompt']) ids.set(name,new Element());
  let stops=0;const stop=new Element();stop.click=()=>{stops++;};ids.set('stop',stop);
  const rpc=async(action,payload)=> {
    calls.push({action,payload});
    if (action === 'cs5_list') {
      const last = Number.isInteger(payload?.before) ? payload.before : 45;
      const start = Math.max(0, last - 20);
      return {status:'LOCAL_RECORDS_NOT_E11',count:45,showing:last-start,
        start_index:start,next_before:start>0?start:null,events:[
          {block:'B02',kind:'idea',text:'Original idea',created_at_utc:'2026-10-30T01:00:00Z',
            evidence_status:'LOCAL_RECORD_ONLY',sha256:'abcdef01',source_url:'https://example.org/source'},
          {block:'B05',kind:'receipt',text:'Unverified source',created_at_utc:'2026-10-30T01:01:00Z',
            evidence_status:'REPORTED_UNVERIFIED',sha256:'abcdef02',source_url:'javascript:alert(1)'}
        ]};
    }
    return {status:'LOCAL',action};
  };
  const navigate=what=>{navEvents.push(what);activeScreen=what;};
  const task=async(action,payload,target)=>{actions.push({action,payload,target});return {status:'ACCEPTED'};};
  runInNewContext(source,{document,rpc,navigate,task,URL});
  return {ids,calls,nav,main,navEvents,actions,
    setActiveScreen: value=>{activeScreen=value;},
    get stops(){return stops;}};
}

test('BACK restores the actual previous NOX Studio screen instead of always Create',async()=>{
  const c=mount();
  c.setActiveScreen('jobs');
  c.nav.children[0].click();
  c.ids.get('cs5-back').click();
  assert.deepEqual(c.navEvents, ['five','jobs']);
  c.setActiveScreen('theater');
  c.nav.children[0].click();
  c.ids.get('cs5-back').click();
  assert.deepEqual(c.navEvents, ['five','jobs','five','theater']);
});

test('CS5 mounts only inside the original Creative nav/content, not HOME/MENU',async()=>{
  const c=mount();
  assert.equal(c.nav.children.length,1);
  assert.equal(c.main.children.length,1);
  assert.equal(c.nav.children[0].dataset.nav,'five');
  const segments = c.ids.get('cs5-segments');
  assert.equal(segments.children.length, 5);
  assert.deepEqual(segments.children.map(x=>x.dataset.cs5Segment),
    ['B01','B02','B03','B04','B05']);
  segments.children[4].click();
  assert.equal(c.ids.get('cs5-block').value, 'B05');
  assert.equal(segments.children[4]['aria-pressed'], 'true');
  assert.equal(c.calls.length,0,'Creative Worker must not start at page mount');
  // Selecting a Creative project before opening CS5 must not switch projects.
  c.ids.get('project').value='owner-project-42';
  await c.nav.children[0].click();
  assert.equal(c.calls[0].action,'cs5_overview');
  assert.equal(c.ids.get('cs5-project').value,'owner-project-42');
  await c.ids.get('cs5-status').click();
  assert.equal(c.calls.length,2,'explicit retry uses the same Worker, no eager call');
  c.ids.get('cs5-project').value='creative01';
  c.ids.get('cs5-text').value='Original fictional screenplay';
  c.ids.get('cs5-block').value='B03';
  c.ids.get('cs5-block').handlers.change();
  assert.equal(c.ids.get('cs5-kind').children.length,2);
  c.ids.get('cs5-kind').value='production';
  await c.ids.get('cs5-save').click();
  await c.ids.get('cs5-list').click();
  const cards = c.ids.get('cs5-history').children;
  assert.equal(cards.length,2,'history renders existing-style evidence cards');
  assert.equal(cards[0].children.length,4,'valid source has real external link');
  assert.equal(cards[1].children.length,3,'unsafe stored source is never clickable');
  assert.equal(c.ids.get('cs5-older').disabled,false);
  assert.equal(c.ids.get('cs5-latest').disabled,true);
  await c.ids.get('cs5-older').click();
  assert.equal(c.calls.at(-1).payload.before,25);
  assert.equal(c.ids.get('cs5-latest').disabled,false);
  await c.ids.get('cs5-older').click();
  assert.equal(c.calls.at(-1).payload.before,5);
  assert.equal(c.ids.get('cs5-older').disabled,true);
  await c.ids.get('cs5-latest').click();
  assert.equal(c.calls.at(-1).payload.before,undefined);
  assert.equal(c.calls.find(x=>x.action==='cs5_append').payload.block,'B03');
  assert.equal(c.ids.get('project').value,'creative01');

  c.ids.get('cs5-research-source').value='crossref';
  c.ids.get('cs5-research-query').value='film history';
  await c.ids.get('cs5-research').click();
  assert.equal(c.actions.find(x=>x.action==='cs5_research').payload.source,'crossref');
  await c.ids.get('cs5-export').click();
  assert.equal(c.calls.at(-1).action,'cs5_export');
  await c.ids.get('cs5-storyboard').click();
  await c.ids.get('cs5-music').click();
  await c.ids.get('cs5-files').click();
  assert.deepEqual(c.actions.map(x=>x.action),['cs5_research','storyboard','create_text','project_files']);
  assert.ok(c.actions.every(x=>x.target==='cs5-result'));
  assert.ok(c.actions.every(x=>x.payload.project_id==='creative01'));

  await c.ids.get('cs5-produce').click();
  await c.ids.get('cs5-models').click();
  await c.ids.get('cs5-back').click();
  assert.deepEqual(c.navEvents,['five','create','models','create']);
  assert.equal(c.ids.get('project').value,'creative01');
  assert.equal(c.ids.get('prompt').value,'Original fictional screenplay');
  await c.ids.get('cs5-stop').click();
  assert.equal(c.stops,1);
});
