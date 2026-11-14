/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var I=globalThis,N=I.ShadowRoot&&(I.ShadyCSS===void 0||I.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,W=Symbol(),oe=new WeakMap,x=class{constructor(e,t,s){if(this._$cssResult$=!0,s!==W)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(N&&e===void 0){let s=t!==void 0&&t.length===1;s&&(e=oe.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),s&&oe.set(t,e))}return e}toString(){return this.cssText}},ie=o=>new x(typeof o=="string"?o:o+"",void 0,W),V=(o,...e)=>{let t=o.length===1?o[0]:e.reduce((s,r,i)=>s+(n=>{if(n._$cssResult$===!0)return n.cssText;if(typeof n=="number")return n;throw Error("Value passed to 'css' function must be a 'css' function result: "+n+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+o[i+1],o[0]);return new x(t,o,W)},ne=(o,e)=>{if(N)o.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let s=document.createElement("style"),r=I.litNonce;r!==void 0&&s.setAttribute("nonce",r),s.textContent=t.cssText,o.appendChild(s)}},G=N?o=>o:o=>o instanceof CSSStyleSheet?(e=>{let t="";for(let s of e.cssRules)t+=s.cssText;return ie(t)})(o):o;/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var{is:Se,defineProperty:Ce,getOwnPropertyDescriptor:xe,getOwnPropertyNames:Ee,getOwnPropertySymbols:Le,getPrototypeOf:we}=Object,f=globalThis,ae=f.trustedTypes,ke=ae?ae.emptyScript:"",Pe=f.reactiveElementPolyfillSupport,E=(o,e)=>o,L={toAttribute(o,e){switch(e){case Boolean:o=o?ke:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,e){let t=o;switch(e){case Boolean:t=o!==null;break;case Number:t=o===null?null:Number(o);break;case Object:case Array:try{t=JSON.parse(o)}catch{t=null}}return t}},q=(o,e)=>!Se(o,e),le={attribute:!0,type:String,converter:L,reflect:!1,useDefault:!1,hasChanged:q};Symbol.metadata??(Symbol.metadata=Symbol("metadata")),f.litPropertyMetadata??(f.litPropertyMetadata=new WeakMap);var m=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??(this.l=[])).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=le){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let s=Symbol(),r=this.getPropertyDescriptor(e,s,t);r!==void 0&&Ce(this.prototype,e,r)}}static getPropertyDescriptor(e,t,s){let{get:r,set:i}=xe(this.prototype,e)??{get(){return this[t]},set(n){this[t]=n}};return{get:r,set(n){let l=r?.call(this);i?.call(this,n),this.requestUpdate(e,l,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??le}static _$Ei(){if(this.hasOwnProperty(E("elementProperties")))return;let e=we(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(E("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(E("properties"))){let t=this.properties,s=[...Ee(t),...Le(t)];for(let r of s)this.createProperty(r,t[r])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[s,r]of t)this.elementProperties.set(s,r)}this._$Eh=new Map;for(let[t,s]of this.elementProperties){let r=this._$Eu(t,s);r!==void 0&&this._$Eh.set(r,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let s=new Set(e.flat(1/0).reverse());for(let r of s)t.unshift(G(r))}else e!==void 0&&t.push(G(e));return t}static _$Eu(e,t){let s=t.attribute;return s===!1?void 0:typeof s=="string"?s:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??(this._$EO=new Set)).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let s of t.keys())this.hasOwnProperty(s)&&(e.set(s,this[s]),delete this[s]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return ne(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??(this.renderRoot=this.createRenderRoot()),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,s){this._$AK(e,s)}_$ET(e,t){let s=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,s);if(r!==void 0&&s.reflect===!0){let i=(s.converter?.toAttribute!==void 0?s.converter:L).toAttribute(t,s.type);this._$Em=e,i==null?this.removeAttribute(r):this.setAttribute(r,i),this._$Em=null}}_$AK(e,t){let s=this.constructor,r=s._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let i=s.getPropertyOptions(r),n=typeof i.converter=="function"?{fromAttribute:i.converter}:i.converter?.fromAttribute!==void 0?i.converter:L;this._$Em=r;let l=n.fromAttribute(t,i.type);this[r]=l??this._$Ej?.get(r)??l,this._$Em=null}}requestUpdate(e,t,s,r=!1,i){if(e!==void 0){let n=this.constructor;if(r===!1&&(i=this[e]),s??(s=n.getPropertyOptions(e)),!((s.hasChanged??q)(i,t)||s.useDefault&&s.reflect&&i===this._$Ej?.get(e)&&!this.hasAttribute(n._$Eu(e,s))))return;this.C(e,t,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:s,reflect:r,wrapped:i},n){s&&!(this._$Ej??(this._$Ej=new Map)).has(e)&&(this._$Ej.set(e,n??t??this[e]),i!==!0||n!==void 0)||(this._$AL.has(e)||(this.hasUpdated||s||(t=void 0),this._$AL.set(e,t)),r===!0&&this._$Em!==e&&(this._$Eq??(this._$Eq=new Set)).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??(this.renderRoot=this.createRenderRoot()),this._$Ep){for(let[r,i]of this._$Ep)this[r]=i;this._$Ep=void 0}let s=this.constructor.elementProperties;if(s.size>0)for(let[r,i]of s){let{wrapped:n}=i,l=this[r];n!==!0||this._$AL.has(r)||l===void 0||this.C(r,void 0,i,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(s=>s.hostUpdate?.()),this.update(t)):this._$EM()}catch(s){throw e=!1,this._$EM(),s}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&(this._$Eq=this._$Eq.forEach(t=>this._$ET(t,this[t]))),this._$EM()}updated(e){}firstUpdated(e){}};m.elementStyles=[],m.shadowRootOptions={mode:"open"},m[E("elementProperties")]=new Map,m[E("finalized")]=new Map,Pe?.({ReactiveElement:m}),(f.reactiveElementVersions??(f.reactiveElementVersions=[])).push("2.1.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var k=globalThis,ce=o=>o,H=k.trustedTypes,he=H?H.createPolicy("lit-html",{createHTML:o=>o}):void 0,fe="$lit$",y=`lit$${Math.random().toFixed(9).slice(2)}$`,ye="?"+y,Me=`<${ye}>`,A=document,P=()=>A.createComment(""),M=o=>o===null||typeof o!="object"&&typeof o!="function",ee=Array.isArray,Re=o=>ee(o)||typeof o?.[Symbol.iterator]=="function",K=`[ 	
\f\r]`,w=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,de=/-->/g,pe=/>/g,_=RegExp(`>|${K}(?:([^\\s"'>=/]+)(${K}*=${K}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),ue=/'/g,me=/"/g,be=/^(?:script|style|textarea|title)$/i,te=o=>(e,...t)=>({_$litType$:o,strings:e,values:t}),D=te(1),We=te(2),Ve=te(3),v=Symbol.for("lit-noChange"),h=Symbol.for("lit-nothing"),ge=new WeakMap,$=A.createTreeWalker(A,129);function _e(o,e){if(!ee(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return he!==void 0?he.createHTML(e):e}var Ue=(o,e)=>{let t=o.length-1,s=[],r,i=e===2?"<svg>":e===3?"<math>":"",n=w;for(let l=0;l<t;l++){let a=o[l],d,p,c=-1,u=0;for(;u<a.length&&(n.lastIndex=u,p=n.exec(a),p!==null);)u=n.lastIndex,n===w?p[1]==="!--"?n=de:p[1]!==void 0?n=pe:p[2]!==void 0?(be.test(p[2])&&(r=RegExp("</"+p[2],"g")),n=_):p[3]!==void 0&&(n=_):n===_?p[0]===">"?(n=r??w,c=-1):p[1]===void 0?c=-2:(c=n.lastIndex-p[2].length,d=p[1],n=p[3]===void 0?_:p[3]==='"'?me:ue):n===me||n===ue?n=_:n===de||n===pe?n=w:(n=_,r=void 0);let g=n===_&&o[l+1].startsWith("/>")?" ":"";i+=n===w?a+Me:c>=0?(s.push(d),a.slice(0,c)+fe+a.slice(c)+y+g):a+y+(c===-2?l:g)}return[_e(o,i+(o[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),s]},R=class o{constructor({strings:e,_$litType$:t},s){let r;this.parts=[];let i=0,n=0,l=e.length-1,a=this.parts,[d,p]=Ue(e,t);if(this.el=o.createElement(d,s),$.currentNode=this.el.content,t===2||t===3){let c=this.el.content.firstChild;c.replaceWith(...c.childNodes)}for(;(r=$.nextNode())!==null&&a.length<l;){if(r.nodeType===1){if(r.hasAttributes())for(let c of r.getAttributeNames())if(c.endsWith(fe)){let u=p[n++],g=r.getAttribute(c).split(y),T=/([.?@])?(.*)/.exec(u);a.push({type:1,index:i,name:T[2],strings:g,ctor:T[1]==="."?Q:T[1]==="?"?Z:T[1]==="@"?Y:C}),r.removeAttribute(c)}else c.startsWith(y)&&(a.push({type:6,index:i}),r.removeAttribute(c));if(be.test(r.tagName)){let c=r.textContent.split(y),u=c.length-1;if(u>0){r.textContent=H?H.emptyScript:"";for(let g=0;g<u;g++)r.append(c[g],P()),$.nextNode(),a.push({type:2,index:++i});r.append(c[u],P())}}}else if(r.nodeType===8)if(r.data===ye)a.push({type:2,index:i});else{let c=-1;for(;(c=r.data.indexOf(y,c+1))!==-1;)a.push({type:7,index:i}),c+=y.length-1}i++}}static createElement(e,t){let s=A.createElement("template");return s.innerHTML=e,s}};function S(o,e,t=o,s){if(e===v)return e;let r=s!==void 0?t._$Co?.[s]:t._$Cl,i=M(e)?void 0:e._$litDirective$;return r?.constructor!==i&&(r?._$AO?.(!1),i===void 0?r=void 0:(r=new i(o),r._$AT(o,t,s)),s!==void 0?(t._$Co??(t._$Co=[]))[s]=r:t._$Cl=r),r!==void 0&&(e=S(o,r._$AS(o,e.values),r,s)),e}var J=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:s}=this._$AD,r=(e?.creationScope??A).importNode(t,!0);$.currentNode=r;let i=$.nextNode(),n=0,l=0,a=s[0];for(;a!==void 0;){if(n===a.index){let d;a.type===2?d=new U(i,i.nextSibling,this,e):a.type===1?d=new a.ctor(i,a.name,a.strings,this,e):a.type===6&&(d=new X(i,this,e)),this._$AV.push(d),a=s[++l]}n!==a?.index&&(i=$.nextNode(),n++)}return $.currentNode=A,r}p(e){let t=0;for(let s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(e,s,t),t+=s.strings.length-2):s._$AI(e[t])),t++}},U=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,s,r){this.type=2,this._$AH=h,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=s,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=S(this,e,t),M(e)?e===h||e==null||e===""?(this._$AH!==h&&this._$AR(),this._$AH=h):e!==this._$AH&&e!==v&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Re(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==h&&M(this._$AH)?this._$AA.nextSibling.data=e:this.T(A.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:s}=e,r=typeof s=="number"?this._$AC(e):(s.el===void 0&&(s.el=R.createElement(_e(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===r)this._$AH.p(t);else{let i=new J(r,this),n=i.u(this.options);i.p(t),this.T(n),this._$AH=i}}_$AC(e){let t=ge.get(e.strings);return t===void 0&&ge.set(e.strings,t=new R(e)),t}k(e){ee(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,s,r=0;for(let i of e)r===t.length?t.push(s=new o(this.O(P()),this.O(P()),this,this.options)):s=t[r],s._$AI(i),r++;r<t.length&&(this._$AR(s&&s._$AB.nextSibling,r),t.length=r)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let s=ce(e).nextSibling;ce(e).remove(),e=s}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},C=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,s,r,i){this.type=1,this._$AH=h,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=i,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=h}_$AI(e,t=this,s,r){let i=this.strings,n=!1;if(i===void 0)e=S(this,e,t,0),n=!M(e)||e!==this._$AH&&e!==v,n&&(this._$AH=e);else{let l=e,a,d;for(e=i[0],a=0;a<i.length-1;a++)d=S(this,l[s+a],t,a),d===v&&(d=this._$AH[a]),n||(n=!M(d)||d!==this._$AH[a]),d===h?e=h:e!==h&&(e+=(d??"")+i[a+1]),this._$AH[a]=d}n&&!r&&this.j(e)}j(e){e===h?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},Q=class extends C{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===h?void 0:e}},Z=class extends C{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==h)}},Y=class extends C{constructor(e,t,s,r,i){super(e,t,s,r,i),this.type=5}_$AI(e,t=this){if((e=S(this,e,t,0)??h)===v)return;let s=this._$AH,r=e===h&&s!==h||e.capture!==s.capture||e.once!==s.once||e.passive!==s.passive,i=e!==h&&(s===h||r);r&&this.element.removeEventListener(this.name,this,s),i&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},X=class{constructor(e,t,s){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(e){S(this,e)}};var Oe=k.litHtmlPolyfillSupport;Oe?.(R,U),(k.litHtmlVersions??(k.litHtmlVersions=[])).push("3.3.3");var $e=(o,e,t)=>{let s=t?.renderBefore??e,r=s._$litPart$;if(r===void 0){let i=t?.renderBefore??null;s._$litPart$=r=new U(e.insertBefore(P(),i),i,void 0,t??{})}return r._$AI(o),r};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var O=globalThis,b=class extends m{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){var t;let e=super.createRenderRoot();return(t=this.renderOptions).renderBefore??(t.renderBefore=e.firstChild),e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=$e(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return v}};b._$litElement$=!0,b.finalized=!0,O.litElementHydrateSupport?.({LitElement:b});var Te=O.litElementPolyfillSupport;Te?.({LitElement:b});(O.litElementVersions??(O.litElementVersions=[])).push("4.2.2");/**
 * @license
 * Copyright 2022 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var Ie={attribute:!0,type:String,converter:L,reflect:!1,hasChanged:q},Ne=(o=Ie,e,t)=>{let{kind:s,metadata:r}=t,i=globalThis.litPropertyMetadata.get(r);if(i===void 0&&globalThis.litPropertyMetadata.set(r,i=new Map),s==="setter"&&((o=Object.create(o)).wrapped=!0),i.set(t.name,o),s==="accessor"){let{name:n}=t;return{set(l){let a=e.get.call(this);e.set.call(this,l),this.requestUpdate(n,a,o,!0,l)},init(l){return l!==void 0&&this.C(n,void 0,o,l),l}}}if(s==="setter"){let{name:n}=t;return function(l){let a=this[n];e.call(this,l),this.requestUpdate(n,a,o,!0,l)}}throw Error("Unsupported decorator location: "+s)};function B(o){return(e,t)=>typeof t=="object"?Ne(o,e,t):((s,r,i)=>{let n=r.hasOwnProperty(i);return r.constructor.createProperty(i,s),n?Object.getOwnPropertyDescriptor(r,i):void 0})(o,e,t)}/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2021 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var qe={"actionCopy.label":"Copy message","actionCopy.copied":"Copied","actionEdit.triggerLabel":"Edit message","actionEdit.textareaLabel":"Edit message","actionEdit.submitLabel":"Save & Submit","actionEdit.cancelLabel":"Cancel","actionEdit.editingBadge":"Editing\u2026","actionFeedback.positiveLabel":"Good response","actionFeedback.negativeLabel":"Bad response","messageActions.toolbarLabel":"Message actions","messageActions.regenerate":"Regenerate response","chatComposer.placeholder":"Type a message...","chatComposer.sendLabel":"Send message","chatComposer.stopLabel":"Stop generation","promptInput.placeholder":"Type a message...","messageItem.showMore":"Show more","messageItem.showLess":"Show less","messageItem.errorText":"Failed to generate response","messageItem.retryLabel":"Retry","messageItem.userAvatar":"You","generationControls.toolbarLabel":"Generation controls","generationControls.stop":"Stop","generationControls.stopLabel":"Stop generation","generationControls.pause":"Pause","generationControls.pauseLabel":"Pause generation","generationControls.resume":"Resume","generationControls.resumeLabel":"Resume generation","typingIndicator.ariaLabel":"AI is typing","typingIndicator.thinkingMessage":"Thinking\u2026","typingIndicator.workingMessage":"Working\u2026","templatePicker.heading":"Choose a template","templatePicker.closeLabel":"Close","templatePicker.searchPlaceholder":"Search templates...","templatePicker.searchLabel":"Search templates","templatePicker.emptyText":"No templates match your search.","modelSelector.placeholder":"Select model...","modelSelector.searchPlaceholder":"Search models...","modelSelector.searchLabel":"Search models","modelSelector.emptyText":"No models found","attachmentChip.pending":"Waiting\u2026","attachmentChip.connecting":"Connecting\u2026","attachmentChip.error":"Error","attachmentChip.uploadError":"Upload error","attachmentChip.retryLabel":"Retry upload {filename}","attachmentChip.removeLabel":"Remove {filename}","attachmentPanel.triggerLabel":"Add files","attachmentPanel.dropOverlay":"Drop files here","messageAttachments.removeLabel":"Remove {filename}","messageAttachments.moreCount":"+{count} more","suggestionChips.ariaLabel":"Suggestions","suggestionChips.moreCount":"+{count} more","nudgeBanner.dismissLabel":"Dismiss","dropdownSelect.placeholder":"Select...","dropdownSelect.searchPlaceholder":"Search...","filterBar.ariaLabel":"Filters","filterBar.excludeLabel":"Exclude:","filterBar.excludePlaceholder":"Topics to avoid...","modeSelector.ariaLabel":"Chat mode","modeSelector.selectLabel":"Select mode","parameterPanel.showAdvanced":"Show advanced","parameterPanel.hideAdvanced":"Hide advanced","dropZone.label":"Drop files to upload","welcomeScreen.heading":"How can I help you?","caveatNotice.message":"AI can make mistakes. Check important info.","chatHeader.agentName":"AI Assistant","disclosureBadge.generated":"Generated by {agent}","disclosureBadge.summarized":"Summarized by {agent}","disclosureBadge.rewrote":"Rewritten by {agent}","disclosureBadge.suggested":"Suggested by {agent}","messageAvatar.altFallback":"Avatar","messageAvatar.namedAlt":"{name} avatar","messageAvatar.aiAlt":"AI avatar","scrollAnchor.label":"Scroll to bottom","confidenceIndicator.labelDefault":"Confidence","confidenceIndicator.levelLow":"low","confidenceIndicator.levelMedium":"medium","confidenceIndicator.levelHigh":"high","uncertaintyMarker.tipUnsure":"Model is uncertain about this claim","uncertaintyMarker.tipNeedsVerification":"This statement needs verification","uncertaintyMarker.tipSpeculative":"Speculative \u2014 not directly grounded in sources","feedbackForm.groupLabel":"Rate this response","feedbackForm.reasonsGroupLabel":"Reason","feedbackForm.helpfulLabel":"Helpful","feedbackForm.notHelpfulLabel":"Not helpful","feedbackForm.sendLabel":"Send","feedbackForm.cancelLabel":"Cancel","feedbackForm.placeholderUp":"What did you like? (optional)","feedbackForm.placeholderDown":"What went wrong? (optional)","feedbackForm.thanksMessage":"Thanks \u2014 your feedback was sent.","feedbackForm.reasonAccurate":"Accurate","feedbackForm.reasonWellWritten":"Well-written","feedbackForm.reasonHelpful":"Helpful","feedbackForm.reasonInaccurate":"Inaccurate","feedbackForm.reasonOffTopic":"Off-topic","feedbackForm.reasonUnsafe":"Unsafe","feedbackForm.reasonOther":"Other","correctionInput.originalLabel":"Original","correctionInput.correctionLabel":"Correction","correctionInput.reasonLabel":"Why is this wrong?","correctionInput.reasonPlaceholder":"Brief explanation","correctionInput.correctionPlaceholder":"Provide the correct version\u2026","correctionInput.submitLabel":"Submit correction","correctionInput.cancelLabel":"Cancel","correctionInput.reasonRequiredMark":"*","disagreementMarker.title":"User disagreed with this response","disagreementMarker.markResolvedLabel":"Mark resolved","disagreementMarker.inlineLabel":"Disagreement","reasoningBlock.thinking":"Thinking\u2026","reasoningBlock.thoughtFor":"Thought for {seconds}s","reasoningBlock.thoughtForMinutes":"Thought for {minutes}m {seconds}s","reasoningBlock.tokensSuffix":"\xB7 {count} tokens","reasoningBlock.expandLabel":"Show reasoning","reasoningBlock.collapseLabel":"Hide reasoning","toolCall.statusQueued":"Queued","toolCall.statusRunning":"Running","toolCall.statusDone":"Done","toolCall.statusFailed":"Failed","toolCall.argumentsLabel":"Arguments","toolCall.resultLabel":"Result","toolCall.errorLabel":"Error","toolCall.expandLabel":"Expand tool call","toolCall.collapseLabel":"Collapse tool call","toolCallList.summaryFallback":"Used {count} tools","toolCallList.summaryFallbackOne":"Used 1 tool","toolCallList.expandLabel":"Show tool calls","toolCallList.collapseLabel":"Hide tool calls","sourceList.heading":"{count} sources","sourceList.headingOne":"1 source","sourceList.openLabel":"Open source {index}","searchInput.placeholder":"Search or ask anything...","searchInput.plainPlaceholder":"Search...","searchInput.askLabel":"Ask AI","searchInput.clearLabel":"Clear search","searchFooter.ariaLabel":"Search keyboard shortcuts","searchAnswer.title":"AI Answer","searchAnswer.generatedBy":"Generated by {model}","searchAnswer.copyLabel":"Copy","searchAnswer.regenerateLabel":"Regenerate","searchAnswer.sourcesLabel":"Cited sources","searchSources.ariaLabel":"Search sources","searchSources.searchingSources":"Searching {count} sources...","searchSources.resultsSoFar":"{count} results so far","searchSources.allLabel":"All","searchSources.errorLabel":"error","searchResults.empty":"No results found.","searchResults.unknownSource":"Unknown source","searchResults.resultCount":"{count} results","searchResults.resultCountOne":"1 result","searchDialog.heading":"Search","searchDialog.closeLabel":"Close search","searchPanel.heading":"Search results"},re=class{constructor(){this._overrides={},this._subscribers=new Set,this._pendingNotify=!1}setLocale(e){this._overrides={...e},this._scheduleNotify()}updateLocale(e){Object.assign(this._overrides,e),this._scheduleNotify()}resetLocale(){this._overrides={},this._scheduleNotify()}getLocale(){return{...this._overrides}}term(e,t){let s=this._overrides[e]??qe[e];if(t)for(let[r,i]of Object.entries(t))s=s.replaceAll(`{${r}}`,String(i));return s}subscribe(e){this._subscribers.add(e)}unsubscribe(e){this._subscribers.delete(e)}_scheduleNotify(){this._pendingNotify||(this._pendingNotify=!0,queueMicrotask(()=>{this._pendingNotify=!1,this._subscribers.forEach(e=>{try{e.requestUpdate()}catch{}})}))}},se=new re;var j=class{constructor(e){this._host=e,e.addController(this)}hostConnected(){se.subscribe(this._host),this._host.requestUpdate()}hostDisconnected(){se.unsubscribe(this._host)}term(e,t){return se.term(e,t)}};var He=V`
  :host {
    display: inline-flex;
  }

  .container {
    display: inline-flex;
    align-items: center;
    gap: var(--loquix-typing-gap, 0.5rem);
    padding: var(--loquix-typing-padding, 0.5rem 0.75rem);
    background: var(--loquix-typing-bg, var(--loquix-surface-secondary-bg, #f9fafb));
    border-radius: var(--loquix-typing-border-radius, var(--loquix-border-radius, 12px));
    font-family: var(--loquix-font-family, sans-serif);
    font-size: var(--loquix-typing-font-size, 0.8125rem);
    color: var(--loquix-typing-text-color, var(--loquix-text-secondary-color, #6b7280));
    line-height: 1.4;
  }

  /* --- Dots variant --- */
  .dots {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  .dot {
    width: var(--loquix-typing-dot-size, 6px);
    height: var(--loquix-typing-dot-size, 6px);
    border-radius: 50%;
    background: var(--loquix-typing-dot-color, var(--loquix-ai-color, #7c3aed));
    animation: loquix-bounce 1.4s ease-in-out infinite both;
  }

  .dot:nth-child(1) {
    animation-delay: 0s;
  }

  .dot:nth-child(2) {
    animation-delay: 0.16s;
  }

  .dot:nth-child(3) {
    animation-delay: 0.32s;
  }

  @keyframes loquix-bounce {
    0%,
    80%,
    100% {
      transform: scale(0);
      opacity: 0.4;
    }
    40% {
      transform: scale(1);
      opacity: 1;
    }
  }

  /* --- Text / Steps variants --- */
  .text {
    color: inherit;
  }
`,De=Object.defineProperty,Ae=(o,e,t,s)=>{for(var r=void 0,i=o.length-1,n;i>=0;i--)(n=o[i])&&(r=n(e,t,r)||r);return r&&De(e,t,r),r},ve=class extends b{constructor(){super(...arguments),this._localize=new j(this),this.variant="dots"}_renderDots(){return D`
      <span class="dots" aria-hidden="true">
        <span part="dot" class="dot"></span>
        <span part="dot" class="dot"></span>
        <span part="dot" class="dot"></span>
      </span>
    `}render(){let e=this.variant==="dots",t=this.variant==="text"?this.message??this._localize.term("typingIndicator.thinkingMessage"):this.variant==="steps"?this.message??this._localize.term("typingIndicator.workingMessage"):h;return D`
      <div
        part="container"
        class="container"
        role="status"
        aria-label="${e?this._localize.term("typingIndicator.ariaLabel"):""}"
      >
        ${e?this._renderDots():h}
        ${t!==h?D`<span class="text">${t}</span>`:h}
      </div>
    `}};ve.styles=[He];var z=ve;Ae([B({type:String,reflect:!0})],z.prototype,"variant");Ae([B({type:String})],z.prototype,"message");customElements.get("loquix-typing-indicator")||customElements.define("loquix-typing-indicator",z);
