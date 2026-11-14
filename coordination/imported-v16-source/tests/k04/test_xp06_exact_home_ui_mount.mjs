import test from 'node:test';
import assert from 'node:assert/strict';
import {mountOneHostMenu} from '../../ui/onehost-menu-bindings.mjs';

function tryMount(location) {
  let subscriptions = 0;
  const webview = {
    postMessage(){},
    addEventListener(){ subscriptions++; },
    removeEventListener(){}
  };
  const windowRef = {
    location: {origin:'https://nox.local', ...location},
    chrome: {webview},
    crypto: {getRandomValues(bytes){bytes.fill(1);return bytes}}
  };
  // Deliberately incomplete DOM: a non-HOME document must be rejected BEFORE
  // the menu or IPC subscriber tries to touch any DOM API.
  const documentRef = {
    getElementById(){return null},
    createElement(){throw Error('HOME_PATH_REACHED_DOM')}
  };
  return {run:()=>mountOneHostMenu({documentRef,windowRef}), subscriptions:()=>subscriptions};
}

test('mapped same-origin non-HOME pages never attach the WebView2 JS bridge',()=>{
  for (const location of [
    {pathname:'/unreviewed.html', search:'', hash:''},
    {pathname:'/',search:'?source=external',hash:''},
    {pathname:'/',search:'',hash:'#fragment'}
  ]) {
    const fixture=tryMount(location);
    assert.equal(fixture.run(),null,'non-HOME must fail closed without DOM access');
    assert.equal(fixture.subscriptions(),0,'no native message listener may attach');
  }
});

test('exact original HOME still reaches existing native bridge without new host',()=>{
  const fixture=tryMount({pathname:'/',search:'',hash:''});
  assert.throws(fixture.run,/HOME_PATH_REACHED_DOM/);
  assert.equal(fixture.subscriptions(),1,'approved HOME still enters the existing bridge');
});
