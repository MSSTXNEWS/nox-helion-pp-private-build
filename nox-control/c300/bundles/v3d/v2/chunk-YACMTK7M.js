import{a as d,d as p}from"./chunk-IKBRAUHY.js";var w=d(V=>{"use strict";var f=p();function q(e,u){return e===u&&(e!==0||1/e===1/u)||e!==e&&u!==u}var z=typeof Object.is=="function"?Object.is:q,I=f.useState,M=f.useEffect,_=f.useLayoutEffect,g=f.useDebugValue;function G(e,u){var t=u(),s=I({inst:{value:t,getSnapshot:u}}),r=s[0].inst,n=s[1];return _(function(){r.value=t,r.getSnapshot=u,E(r)&&n({inst:r})},[e,t,u]),M(function(){return E(r)&&n({inst:r}),e(function(){E(r)&&n({inst:r})})},[e]),g(t),t}function E(e){var u=e.getSnapshot;e=e.value;try{var t=u();return!z(e,t)}catch{return!0}}function L(e,u){return u()}var $=typeof window>"u"||typeof window.document>"u"||typeof window.document.createElement>"u"?L:G;V.useSyncExternalStore=f.useSyncExternalStore!==void 0?f.useSyncExternalStore:$});var D=d((P,h)=>{"use strict";h.exports=w()});var R=d(O=>{"use strict";var m=p(),k=D();function C(e,u){return e===u&&(e!==0||1/e===1/u)||e!==e&&u!==u}var U=typeof Object.is=="function"?Object.is:C,W=k.useSyncExternalStore,A=m.useRef,B=m.useEffect,F=m.useMemo,H=m.useDebugValue;O.useSyncExternalStoreWithSelector=function(e,u,t,s,r){var n=A(null);if(n.current===null){var i={hasValue:!1,value:null};n.current=i}else i=n.current;n=F(function(){function y(o){if(!j){if(j=!0,l=o,o=s(o),r!==void 0&&i.hasValue){var c=i.value;if(r(c,o))return v=c}return v=o}if(c=v,U(l,o))return c;var b=s(o);return r!==void 0&&r(c,b)?(l=o,c):(l=o,v=b)}var j=!1,l,v,S=t===void 0?null:t;return[function(){return y(u())},S===null?void 0:function(){return y(S())}]},[u,t,s,r]);var a=W(e,n[0],n[1]);return B(function(){i.hasValue=!0,i.value=a},[a]),H(a),a}});var J=d((T,N)=>{"use strict";N.exports=R()});export{J as a};
/*! Bundled license information:

use-sync-external-store/cjs/use-sync-external-store-shim.production.js:
  (**
   * @license React
   * use-sync-external-store-shim.production.js
   *
   * Copyright (c) Meta Platforms, Inc. and affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)

use-sync-external-store/cjs/use-sync-external-store-shim/with-selector.production.js:
  (**
   * @license React
   * use-sync-external-store-shim/with-selector.production.js
   *
   * Copyright (c) Meta Platforms, Inc. and affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)
*/
