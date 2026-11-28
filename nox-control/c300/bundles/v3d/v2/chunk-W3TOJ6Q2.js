import{A as Lt,B as At,C as N,D as P,E as bt,F as Mt,G as Pt,H as Ut,I as wt,a as xt,b as Et,d as J,e as vt,h as Z,i as K,j as M,k as x,l as X,m as tt,n as Tt,o as b,p as nt,q as Ot,s as at,t as z,u as lt,v as B,x as St,y as Ct,z as q}from"./chunk-TV7R54GY.js";import"./chunk-DG7ZX5K5.js";import"./chunk-YACMTK7M.js";import{c as j,d as W}from"./chunk-IKBRAUHY.js";var a=j(W());function V(){return V=Object.assign?Object.assign.bind():function(r){for(var t=1;t<arguments.length;t++){var e=arguments[t];for(var i in e)({}).hasOwnProperty.call(e,i)&&(r[i]=e[i])}return r},V.apply(null,arguments)}var et=parseInt("170".replace(/\D+/g,""));var ct=et>=125?"uv1":"uv2";var Dt=new X,ot=new x,F=class extends Ct{constructor(){super(),this.isLineSegmentsGeometry=!0,this.type="LineSegmentsGeometry";let t=[-1,2,0,1,2,0,-1,1,0,1,1,0,-1,0,0,1,0,0,-1,-1,0,1,-1,0],e=[-1,2,1,2,-1,1,1,1,-1,-1,1,-1,-1,-2,1,-2],i=[0,2,1,2,3,1,2,4,3,4,5,3,4,6,5,6,7,5];this.setIndex(i),this.setAttribute("position",new nt(t,3)),this.setAttribute("uv",new nt(e,2))}applyMatrix4(t){let e=this.attributes.instanceStart,i=this.attributes.instanceEnd;return e!==void 0&&(e.applyMatrix4(t),i.applyMatrix4(t),e.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}setPositions(t){let e;t instanceof Float32Array?e=t:Array.isArray(t)&&(e=new Float32Array(t));let i=new q(e,6,1);return this.setAttribute("instanceStart",new B(i,3,0)),this.setAttribute("instanceEnd",new B(i,3,3)),this.computeBoundingBox(),this.computeBoundingSphere(),this}setColors(t,e=3){let i;t instanceof Float32Array?i=t:Array.isArray(t)&&(i=new Float32Array(t));let o=new q(i,e*2,1);return this.setAttribute("instanceColorStart",new B(o,e,0)),this.setAttribute("instanceColorEnd",new B(o,e,e)),this}fromWireframeGeometry(t){return this.setPositions(t.attributes.position.array),this}fromEdgesGeometry(t){return this.setPositions(t.attributes.position.array),this}fromMesh(t){return this.fromWireframeGeometry(new St(t.geometry)),this}fromLineSegments(t){let e=t.geometry;return this.setPositions(e.attributes.position.array),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new X);let t=this.attributes.instanceStart,e=this.attributes.instanceEnd;t!==void 0&&e!==void 0&&(this.boundingBox.setFromBufferAttribute(t),Dt.setFromBufferAttribute(e),this.boundingBox.union(Dt))}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new tt),this.boundingBox===null&&this.computeBoundingBox();let t=this.attributes.instanceStart,e=this.attributes.instanceEnd;if(t!==void 0&&e!==void 0){let i=this.boundingSphere.center;this.boundingBox.getCenter(i);let o=0;for(let s=0,c=t.count;s<c;s++)ot.fromBufferAttribute(t,s),o=Math.max(o,i.distanceToSquared(ot)),ot.fromBufferAttribute(e,s),o=Math.max(o,i.distanceToSquared(ot));this.boundingSphere.radius=Math.sqrt(o),isNaN(this.boundingSphere.radius)&&console.error("THREE.LineSegmentsGeometry.computeBoundingSphere(): Computed radius is NaN. The instanced position data is likely to have NaN values.",this)}}toJSON(){}applyMatrix(t){return console.warn("THREE.LineSegmentsGeometry: applyMatrix() has been renamed to applyMatrix4()."),this.applyMatrix4(t)}};var k=class extends F{constructor(){super(),this.isLineGeometry=!0,this.type="LineGeometry"}setPositions(t){let e=t.length-3,i=new Float32Array(2*e);for(let o=0;o<e;o+=3)i[2*o]=t[o],i[2*o+1]=t[o+1],i[2*o+2]=t[o+2],i[2*o+3]=t[o+3],i[2*o+4]=t[o+4],i[2*o+5]=t[o+5];return super.setPositions(i),this}setColors(t,e=3){let i=t.length-e,o=new Float32Array(2*i);if(e===3)for(let s=0;s<i;s+=e)o[2*s]=t[s],o[2*s+1]=t[s+1],o[2*s+2]=t[s+2],o[2*s+3]=t[s+3],o[2*s+4]=t[s+4],o[2*s+5]=t[s+5];else for(let s=0;s<i;s+=e)o[2*s]=t[s],o[2*s+1]=t[s+1],o[2*s+2]=t[s+2],o[2*s+3]=t[s+3],o[2*s+4]=t[s+4],o[2*s+5]=t[s+5],o[2*s+6]=t[s+6],o[2*s+7]=t[s+7];return super.setColors(o,e),this}fromLine(t){let e=t.geometry;return this.setPositions(e.attributes.position.array),this}};var H=class extends z{constructor(t){super({type:"LineMaterial",uniforms:at.clone(at.merge([lt.common,lt.fog,{worldUnits:{value:1},linewidth:{value:1},resolution:{value:new K(1,1)},dashOffset:{value:0},dashScale:{value:1},dashSize:{value:1},gapSize:{value:1}}])),vertexShader:`
				#include <common>
				#include <fog_pars_vertex>
				#include <logdepthbuf_pars_vertex>
				#include <clipping_planes_pars_vertex>

				uniform float linewidth;
				uniform vec2 resolution;

				attribute vec3 instanceStart;
				attribute vec3 instanceEnd;

				#ifdef USE_COLOR
					#ifdef USE_LINE_COLOR_ALPHA
						varying vec4 vLineColor;
						attribute vec4 instanceColorStart;
						attribute vec4 instanceColorEnd;
					#else
						varying vec3 vLineColor;
						attribute vec3 instanceColorStart;
						attribute vec3 instanceColorEnd;
					#endif
				#endif

				#ifdef WORLD_UNITS

					varying vec4 worldPos;
					varying vec3 worldStart;
					varying vec3 worldEnd;

					#ifdef USE_DASH

						varying vec2 vUv;

					#endif

				#else

					varying vec2 vUv;

				#endif

				#ifdef USE_DASH

					uniform float dashScale;
					attribute float instanceDistanceStart;
					attribute float instanceDistanceEnd;
					varying float vLineDistance;

				#endif

				void trimSegment( const in vec4 start, inout vec4 end ) {

					// trim end segment so it terminates between the camera plane and the near plane

					// conservative estimate of the near plane
					float a = projectionMatrix[ 2 ][ 2 ]; // 3nd entry in 3th column
					float b = projectionMatrix[ 3 ][ 2 ]; // 3nd entry in 4th column
					float nearEstimate = - 0.5 * b / a;

					float alpha = ( nearEstimate - start.z ) / ( end.z - start.z );

					end.xyz = mix( start.xyz, end.xyz, alpha );

				}

				void main() {

					#ifdef USE_COLOR

						vLineColor = ( position.y < 0.5 ) ? instanceColorStart : instanceColorEnd;

					#endif

					#ifdef USE_DASH

						vLineDistance = ( position.y < 0.5 ) ? dashScale * instanceDistanceStart : dashScale * instanceDistanceEnd;
						vUv = uv;

					#endif

					float aspect = resolution.x / resolution.y;

					// camera space
					vec4 start = modelViewMatrix * vec4( instanceStart, 1.0 );
					vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );

					#ifdef WORLD_UNITS

						worldStart = start.xyz;
						worldEnd = end.xyz;

					#else

						vUv = uv;

					#endif

					// special case for perspective projection, and segments that terminate either in, or behind, the camera plane
					// clearly the gpu firmware has a way of addressing this issue when projecting into ndc space
					// but we need to perform ndc-space calculations in the shader, so we must address this issue directly
					// perhaps there is a more elegant solution -- WestLangley

					bool perspective = ( projectionMatrix[ 2 ][ 3 ] == - 1.0 ); // 4th entry in the 3rd column

					if ( perspective ) {

						if ( start.z < 0.0 && end.z >= 0.0 ) {

							trimSegment( start, end );

						} else if ( end.z < 0.0 && start.z >= 0.0 ) {

							trimSegment( end, start );

						}

					}

					// clip space
					vec4 clipStart = projectionMatrix * start;
					vec4 clipEnd = projectionMatrix * end;

					// ndc space
					vec3 ndcStart = clipStart.xyz / clipStart.w;
					vec3 ndcEnd = clipEnd.xyz / clipEnd.w;

					// direction
					vec2 dir = ndcEnd.xy - ndcStart.xy;

					// account for clip-space aspect ratio
					dir.x *= aspect;
					dir = normalize( dir );

					#ifdef WORLD_UNITS

						// get the offset direction as perpendicular to the view vector
						vec3 worldDir = normalize( end.xyz - start.xyz );
						vec3 offset;
						if ( position.y < 0.5 ) {

							offset = normalize( cross( start.xyz, worldDir ) );

						} else {

							offset = normalize( cross( end.xyz, worldDir ) );

						}

						// sign flip
						if ( position.x < 0.0 ) offset *= - 1.0;

						float forwardOffset = dot( worldDir, vec3( 0.0, 0.0, 1.0 ) );

						// don't extend the line if we're rendering dashes because we
						// won't be rendering the endcaps
						#ifndef USE_DASH

							// extend the line bounds to encompass  endcaps
							start.xyz += - worldDir * linewidth * 0.5;
							end.xyz += worldDir * linewidth * 0.5;

							// shift the position of the quad so it hugs the forward edge of the line
							offset.xy -= dir * forwardOffset;
							offset.z += 0.5;

						#endif

						// endcaps
						if ( position.y > 1.0 || position.y < 0.0 ) {

							offset.xy += dir * 2.0 * forwardOffset;

						}

						// adjust for linewidth
						offset *= linewidth * 0.5;

						// set the world position
						worldPos = ( position.y < 0.5 ) ? start : end;
						worldPos.xyz += offset;

						// project the worldpos
						vec4 clip = projectionMatrix * worldPos;

						// shift the depth of the projected points so the line
						// segments overlap neatly
						vec3 clipPose = ( position.y < 0.5 ) ? ndcStart : ndcEnd;
						clip.z = clipPose.z * clip.w;

					#else

						vec2 offset = vec2( dir.y, - dir.x );
						// undo aspect ratio adjustment
						dir.x /= aspect;
						offset.x /= aspect;

						// sign flip
						if ( position.x < 0.0 ) offset *= - 1.0;

						// endcaps
						if ( position.y < 0.0 ) {

							offset += - dir;

						} else if ( position.y > 1.0 ) {

							offset += dir;

						}

						// adjust for linewidth
						offset *= linewidth;

						// adjust for clip-space to screen-space conversion // maybe resolution should be based on viewport ...
						offset /= resolution.y;

						// select end
						vec4 clip = ( position.y < 0.5 ) ? clipStart : clipEnd;

						// back to clip space
						offset *= clip.w;

						clip.xy += offset;

					#endif

					gl_Position = clip;

					vec4 mvPosition = ( position.y < 0.5 ) ? start : end; // this is an approximation

					#include <logdepthbuf_vertex>
					#include <clipping_planes_vertex>
					#include <fog_vertex>

				}
			`,fragmentShader:`
				uniform vec3 diffuse;
				uniform float opacity;
				uniform float linewidth;

				#ifdef USE_DASH

					uniform float dashOffset;
					uniform float dashSize;
					uniform float gapSize;

				#endif

				varying float vLineDistance;

				#ifdef WORLD_UNITS

					varying vec4 worldPos;
					varying vec3 worldStart;
					varying vec3 worldEnd;

					#ifdef USE_DASH

						varying vec2 vUv;

					#endif

				#else

					varying vec2 vUv;

				#endif

				#include <common>
				#include <fog_pars_fragment>
				#include <logdepthbuf_pars_fragment>
				#include <clipping_planes_pars_fragment>

				#ifdef USE_COLOR
					#ifdef USE_LINE_COLOR_ALPHA
						varying vec4 vLineColor;
					#else
						varying vec3 vLineColor;
					#endif
				#endif

				vec2 closestLineToLine(vec3 p1, vec3 p2, vec3 p3, vec3 p4) {

					float mua;
					float mub;

					vec3 p13 = p1 - p3;
					vec3 p43 = p4 - p3;

					vec3 p21 = p2 - p1;

					float d1343 = dot( p13, p43 );
					float d4321 = dot( p43, p21 );
					float d1321 = dot( p13, p21 );
					float d4343 = dot( p43, p43 );
					float d2121 = dot( p21, p21 );

					float denom = d2121 * d4343 - d4321 * d4321;

					float numer = d1343 * d4321 - d1321 * d4343;

					mua = numer / denom;
					mua = clamp( mua, 0.0, 1.0 );
					mub = ( d1343 + d4321 * ( mua ) ) / d4343;
					mub = clamp( mub, 0.0, 1.0 );

					return vec2( mua, mub );

				}

				void main() {

					#include <clipping_planes_fragment>

					#ifdef USE_DASH

						if ( vUv.y < - 1.0 || vUv.y > 1.0 ) discard; // discard endcaps

						if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX

					#endif

					float alpha = opacity;

					#ifdef WORLD_UNITS

						// Find the closest points on the view ray and the line segment
						vec3 rayEnd = normalize( worldPos.xyz ) * 1e5;
						vec3 lineDir = worldEnd - worldStart;
						vec2 params = closestLineToLine( worldStart, worldEnd, vec3( 0.0, 0.0, 0.0 ), rayEnd );

						vec3 p1 = worldStart + lineDir * params.x;
						vec3 p2 = rayEnd * params.y;
						vec3 delta = p1 - p2;
						float len = length( delta );
						float norm = len / linewidth;

						#ifndef USE_DASH

							#ifdef USE_ALPHA_TO_COVERAGE

								float dnorm = fwidth( norm );
								alpha = 1.0 - smoothstep( 0.5 - dnorm, 0.5 + dnorm, norm );

							#else

								if ( norm > 0.5 ) {

									discard;

								}

							#endif

						#endif

					#else

						#ifdef USE_ALPHA_TO_COVERAGE

							// artifacts appear on some hardware if a derivative is taken within a conditional
							float a = vUv.x;
							float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
							float len2 = a * a + b * b;
							float dlen = fwidth( len2 );

							if ( abs( vUv.y ) > 1.0 ) {

								alpha = 1.0 - smoothstep( 1.0 - dlen, 1.0 + dlen, len2 );

							}

						#else

							if ( abs( vUv.y ) > 1.0 ) {

								float a = vUv.x;
								float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
								float len2 = a * a + b * b;

								if ( len2 > 1.0 ) discard;

							}

						#endif

					#endif

					vec4 diffuseColor = vec4( diffuse, alpha );
					#ifdef USE_COLOR
						#ifdef USE_LINE_COLOR_ALPHA
							diffuseColor *= vLineColor;
						#else
							diffuseColor.rgb *= vLineColor;
						#endif
					#endif

					#include <logdepthbuf_fragment>

					gl_FragColor = diffuseColor;

					#include <tonemapping_fragment>
					#include <${et>=154?"colorspace_fragment":"encodings_fragment"}>
					#include <fog_fragment>
					#include <premultiplied_alpha_fragment>

				}
			`,clipping:!0}),this.isLineMaterial=!0,this.onBeforeCompile=function(){this.transparent?this.defines.USE_LINE_COLOR_ALPHA="1":delete this.defines.USE_LINE_COLOR_ALPHA},Object.defineProperties(this,{color:{enumerable:!0,get:function(){return this.uniforms.diffuse.value},set:function(e){this.uniforms.diffuse.value=e}},worldUnits:{enumerable:!0,get:function(){return"WORLD_UNITS"in this.defines},set:function(e){e===!0?this.defines.WORLD_UNITS="":delete this.defines.WORLD_UNITS}},linewidth:{enumerable:!0,get:function(){return this.uniforms.linewidth.value},set:function(e){this.uniforms.linewidth.value=e}},dashed:{enumerable:!0,get:function(){return"USE_DASH"in this.defines},set(e){!!e!="USE_DASH"in this.defines&&(this.needsUpdate=!0),e===!0?this.defines.USE_DASH="":delete this.defines.USE_DASH}},dashScale:{enumerable:!0,get:function(){return this.uniforms.dashScale.value},set:function(e){this.uniforms.dashScale.value=e}},dashSize:{enumerable:!0,get:function(){return this.uniforms.dashSize.value},set:function(e){this.uniforms.dashSize.value=e}},dashOffset:{enumerable:!0,get:function(){return this.uniforms.dashOffset.value},set:function(e){this.uniforms.dashOffset.value=e}},gapSize:{enumerable:!0,get:function(){return this.uniforms.gapSize.value},set:function(e){this.uniforms.gapSize.value=e}},opacity:{enumerable:!0,get:function(){return this.uniforms.opacity.value},set:function(e){this.uniforms.opacity.value=e}},resolution:{enumerable:!0,get:function(){return this.uniforms.resolution.value},set:function(e){this.uniforms.resolution.value.copy(e)}},alphaToCoverage:{enumerable:!0,get:function(){return"USE_ALPHA_TO_COVERAGE"in this.defines},set:function(e){!!e!="USE_ALPHA_TO_COVERAGE"in this.defines&&(this.needsUpdate=!0),e===!0?(this.defines.USE_ALPHA_TO_COVERAGE="",this.extensions.derivatives=!0):(delete this.defines.USE_ALPHA_TO_COVERAGE,this.extensions.derivatives=!1)}}}),this.setValues(t)}};var ht=new M,Rt=new x,zt=new x,E=new M,v=new M,U=new M,mt=new x,pt=new Tt,T=new At,Ft=new x,rt=new X,it=new tt,w=new M,D,G;function Ht(r,t,e){return w.set(0,0,-t,1).applyMatrix4(r.projectionMatrix),w.multiplyScalar(1/w.w),w.x=G/e.width,w.y=G/e.height,w.applyMatrix4(r.projectionMatrixInverse),w.multiplyScalar(1/w.w),Math.abs(Math.max(w.x,w.y))}function Gt(r,t){let e=r.matrixWorld,i=r.geometry,o=i.attributes.instanceStart,s=i.attributes.instanceEnd,c=Math.min(i.instanceCount,o.count);for(let n=0,h=c;n<h;n++){T.start.fromBufferAttribute(o,n),T.end.fromBufferAttribute(s,n),T.applyMatrix4(e);let m=new x,l=new x;D.distanceSqToSegment(T.start,T.end,l,m),l.distanceTo(m)<G*.5&&t.push({point:l,pointOnLine:m,distance:D.origin.distanceTo(l),object:r,face:null,faceIndex:n,uv:null,[ct]:null})}}function Yt(r,t,e){let i=t.projectionMatrix,s=r.material.resolution,c=r.matrixWorld,n=r.geometry,h=n.attributes.instanceStart,m=n.attributes.instanceEnd,l=Math.min(n.instanceCount,h.count),p=-t.near;D.at(1,U),U.w=1,U.applyMatrix4(t.matrixWorldInverse),U.applyMatrix4(i),U.multiplyScalar(1/U.w),U.x*=s.x/2,U.y*=s.y/2,U.z=0,mt.copy(U),pt.multiplyMatrices(t.matrixWorldInverse,c);for(let u=0,g=l;u<g;u++){if(E.fromBufferAttribute(h,u),v.fromBufferAttribute(m,u),E.w=1,v.w=1,E.applyMatrix4(pt),v.applyMatrix4(pt),E.z>p&&v.z>p)continue;if(E.z>p){let d=E.z-v.z,L=(E.z-p)/d;E.lerp(v,L)}else if(v.z>p){let d=v.z-E.z,L=(v.z-p)/d;v.lerp(E,L)}E.applyMatrix4(i),v.applyMatrix4(i),E.multiplyScalar(1/E.w),v.multiplyScalar(1/v.w),E.x*=s.x/2,E.y*=s.y/2,v.x*=s.x/2,v.y*=s.y/2,T.start.copy(E),T.start.z=0,T.end.copy(v),T.end.z=0;let _=T.closestPointToPointParameter(mt,!0);T.at(_,Ft);let S=Z.lerp(E.z,v.z,_),A=S>=-1&&S<=1,I=mt.distanceTo(Ft)<G*.5;if(A&&I){T.start.fromBufferAttribute(h,u),T.end.fromBufferAttribute(m,u),T.start.applyMatrix4(c),T.end.applyMatrix4(c);let d=new x,L=new x;D.distanceSqToSegment(T.start,T.end,L,d),e.push({point:L,pointOnLine:d,distance:D.origin.distanceTo(L),object:r,face:null,faceIndex:u,uv:null,[ct]:null})}}}var Y=class extends Ot{constructor(t=new F,e=new H({color:Math.random()*16777215})){super(t,e),this.isLineSegments2=!0,this.type="LineSegments2"}computeLineDistances(){let t=this.geometry,e=t.attributes.instanceStart,i=t.attributes.instanceEnd,o=new Float32Array(2*e.count);for(let c=0,n=0,h=e.count;c<h;c++,n+=2)Rt.fromBufferAttribute(e,c),zt.fromBufferAttribute(i,c),o[n]=n===0?0:o[n-1],o[n+1]=o[n]+Rt.distanceTo(zt);let s=new q(o,2,1);return t.setAttribute("instanceDistanceStart",new B(s,1,0)),t.setAttribute("instanceDistanceEnd",new B(s,1,1)),this}raycast(t,e){let i=this.material.worldUnits,o=t.camera;o===null&&!i&&console.error('LineSegments2: "Raycaster.camera" needs to be set in order to raycast against LineSegments2 while worldUnits is set to false.');let s=t.params.Line2!==void 0&&t.params.Line2.threshold||0;D=t.ray;let c=this.matrixWorld,n=this.geometry,h=this.material;G=h.linewidth+s,n.boundingSphere===null&&n.computeBoundingSphere(),it.copy(n.boundingSphere).applyMatrix4(c);let m;if(i)m=G*.5;else{let p=Math.max(o.near,it.distanceToPoint(D.origin));m=Ht(o,p,h.resolution)}if(it.radius+=m,D.intersectsSphere(it)===!1)return;n.boundingBox===null&&n.computeBoundingBox(),rt.copy(n.boundingBox).applyMatrix4(c);let l;if(i)l=G*.5;else{let p=Math.max(o.near,rt.distanceToPoint(D.origin));l=Ht(o,p,h.resolution)}rt.expandByScalar(l),D.intersectsBox(rt)!==!1&&(i?Gt(this,e):Yt(this,o,e))}onBeforeRender(t){let e=this.material.uniforms;e&&e.resolution&&(t.getViewport(ht),this.material.uniforms.resolution.value.set(ht.z,ht.w))}};var Q=class extends Y{constructor(t=new k,e=new H({color:Math.random()*16777215})){super(t,e),this.isLine2=!0,this.type="Line2"}};var O=j(W());var dt=O.forwardRef(function({points:t,color:e=16777215,vertexColors:i,linewidth:o,lineWidth:s,segments:c,dashed:n,...h},m){var l,p;let u=N(A=>A.size),g=O.useMemo(()=>c?new Y:new Q,[c]),[f]=O.useState(()=>new H),_=(i==null||(l=i[0])==null?void 0:l.length)===4?4:3,S=O.useMemo(()=>{let A=c?new F:new k,I=t.map(d=>{let L=Array.isArray(d);return d instanceof x||d instanceof M?[d.x,d.y,d.z]:d instanceof K?[d.x,d.y,0]:L&&d.length===3?[d[0],d[1],d[2]]:L&&d.length===2?[d[0],d[1],0]:d});if(A.setPositions(I.flat()),i){e=16777215;let d=i.map(L=>L instanceof b?L.toArray():L);A.setColors(d.flat(),_)}return A},[t,c,i,_]);return O.useLayoutEffect(()=>{g.computeLineDistances()},[t,g]),O.useLayoutEffect(()=>{n?f.defines.USE_DASH="":delete f.defines.USE_DASH,f.needsUpdate=!0},[n,f]),O.useEffect(()=>()=>{S.dispose(),f.dispose()},[S]),O.createElement("primitive",V({object:g,ref:m},h),O.createElement("primitive",{object:S,attach:"geometry"}),O.createElement("primitive",V({object:f,attach:"material",color:e,vertexColors:!!i,resolution:[u.width,u.height],linewidth:(p=o??s)!==null&&p!==void 0?p:1,dashed:n,transparent:_===4},h)))});var Zt=()=>parseInt("170".replace(/\D+/g,"")),st=Zt();var He=Object.freeze({NONE:0,ROTATE:1,TRUCK:2,SCREEN_PAN:4,OFFSET:8,DOLLY:16,ZOOM:32,TOUCH_ROTATE:64,TOUCH_TRUCK:128,TOUCH_SCREEN_PAN:256,TOUCH_OFFSET:512,TOUCH_DOLLY:1024,TOUCH_ZOOM:2048,TOUCH_DOLLY_TRUCK:4096,TOUCH_DOLLY_SCREEN_PAN:8192,TOUCH_DOLLY_OFFSET:16384,TOUCH_DOLLY_ROTATE:32768,TOUCH_ZOOM_TRUCK:65536,TOUCH_ZOOM_OFFSET:131072,TOUCH_ZOOM_SCREEN_PAN:262144,TOUCH_ZOOM_ROTATE:524288});var Be=Math.PI*2,Ie=Math.PI/2;var Ne=Math.PI/180;var Ve=1/8,ke=/Mac/.test(globalThis?.navigator?.platform);var R=j(W());var ft=R.forwardRef(({children:r,enabled:t=!0,speed:e=1,rotationIntensity:i=1,floatIntensity:o=1,floatingRange:s=[-.1,.1],autoInvalidate:c=!1,...n},h)=>{let m=R.useRef(null);R.useImperativeHandle(h,()=>m.current,[]);let l=R.useRef(Math.random()*1e4);return P(p=>{var u,g;if(!t||e===0)return;c&&p.invalidate();let f=l.current+p.clock.elapsedTime;m.current.rotation.x=Math.cos(f/4*e)/8*i,m.current.rotation.y=Math.sin(f/4*e)/8*i,m.current.rotation.z=Math.sin(f/4*e)/20*i;let _=Math.sin(f/4*e)/10;_=Z.mapLinear(_,-.1,.1,(u=s?.[0])!==null&&u!==void 0?u:-.1,(g=s?.[1])!==null&&g!==void 0?g:.1),m.current.position.y=_*o,m.current.updateMatrix()}),R.createElement("group",n,R.createElement("group",{ref:m,matrixAutoUpdate:!1},r))});var C=j(W());var ut=class extends z{constructor(){super({uniforms:{time:{value:0},fade:{value:1}},vertexShader:`
      uniform float time;
      attribute float size;
      varying vec3 vColor;
      void main() {
        vColor = color;
        vec4 mvPosition = modelViewMatrix * vec4(position, 0.5);
        gl_PointSize = size * (30.0 / -mvPosition.z) * (3.0 + sin(time + 100.0));
        gl_Position = projectionMatrix * mvPosition;
      }`,fragmentShader:`
      uniform sampler2D pointTexture;
      uniform float fade;
      varying vec3 vColor;
      void main() {
        float opacity = 1.0;
        if (fade == 1.0) {
          float d = distance(gl_PointCoord, vec2(0.5, 0.5));
          opacity = 1.0 / (1.0 + exp(16.0 * (d - 0.25)));
        }
        gl_FragColor = vec4(vColor, opacity);

        #include <tonemapping_fragment>
	      #include <${st>=154?"colorspace_fragment":"encodings_fragment"}>
      }`})}},Kt=r=>new x().setFromSpherical(new Lt(r,Math.acos(1-Math.random()*2),Math.random()*2*Math.PI)),_t=C.forwardRef(({radius:r=100,depth:t=50,count:e=5e3,saturation:i=0,factor:o=4,fade:s=!1,speed:c=1},n)=>{let h=C.useRef(null),[m,l,p]=C.useMemo(()=>{let g=[],f=[],_=Array.from({length:e},()=>(.5+.5*Math.random())*o),S=new b,A=r+t,I=t/e;for(let d=0;d<e;d++)A-=I*Math.random(),g.push(...Kt(A).toArray()),S.setHSL(d/e,i,.9),f.push(S.r,S.g,S.b);return[new Float32Array(g),new Float32Array(f),new Float32Array(_)]},[e,t,o,r,i]);P(g=>h.current&&(h.current.uniforms.time.value=g.clock.elapsedTime*c));let[u]=C.useState(()=>new ut);return C.createElement("points",{ref:n},C.createElement("bufferGeometry",null,C.createElement("bufferAttribute",{attach:"attributes-position",args:[m,3]}),C.createElement("bufferAttribute",{attach:"attributes-color",args:[l,3]}),C.createElement("bufferAttribute",{attach:"attributes-size",args:[p,1]})),C.createElement("primitive",{ref:h,object:u,attach:"material",blending:J,"uniforms-fade-value":s,depthWrite:!1,transparent:!0,vertexColors:!0}))});var y=j(W());var gt=class extends z{constructor(){super({uniforms:{time:{value:0},pixelRatio:{value:1}},vertexShader:`
        uniform float pixelRatio;
        uniform float time;
        attribute float size;  
        attribute float speed;  
        attribute float opacity;
        attribute vec3 noise;
        attribute vec3 color;
        varying vec3 vColor;
        varying float vOpacity;

        void main() {
          vec4 modelPosition = modelMatrix * vec4(position, 1.0);
          modelPosition.y += sin(time * speed + modelPosition.x * noise.x * 100.0) * 0.2;
          modelPosition.z += cos(time * speed + modelPosition.x * noise.y * 100.0) * 0.2;
          modelPosition.x += cos(time * speed + modelPosition.x * noise.z * 100.0) * 0.2;
          vec4 viewPosition = viewMatrix * modelPosition;
          vec4 projectionPostion = projectionMatrix * viewPosition;
          gl_Position = projectionPostion;
          gl_PointSize = size * 25. * pixelRatio;
          gl_PointSize *= (1.0 / - viewPosition.z);
          vColor = color;
          vOpacity = opacity;
        }
      `,fragmentShader:`
        varying vec3 vColor;
        varying float vOpacity;
        void main() {
          float distanceToCenter = distance(gl_PointCoord, vec2(0.5));
          float strength = 0.05 / distanceToCenter - 0.1;
          gl_FragColor = vec4(vColor, strength * vOpacity);
          #include <tonemapping_fragment>
          #include <${st>=154?"colorspace_fragment":"encodings_fragment"}>
        }
      `})}get time(){return this.uniforms.time.value}set time(t){this.uniforms.time.value=t}get pixelRatio(){return this.uniforms.pixelRatio.value}set pixelRatio(t){this.uniforms.pixelRatio.value=t}},It=r=>r&&r.constructor===Float32Array,jt=r=>[r.r,r.g,r.b],Nt=r=>r instanceof K||r instanceof x||r instanceof M,Vt=r=>Array.isArray(r)?r:Nt(r)?r.toArray():[r,r,r];function $(r,t,e){return y.useMemo(()=>{if(t!==void 0){if(It(t))return t;if(t instanceof b){let i=Array.from({length:r*3},()=>jt(t)).flat();return Float32Array.from(i)}else if(Nt(t)||Array.isArray(t)){let i=Array.from({length:r*3},()=>Vt(t)).flat();return Float32Array.from(i)}return Float32Array.from({length:r},()=>t)}return Float32Array.from({length:r},e)},[t])}var yt=y.forwardRef(({noise:r=1,count:t=100,speed:e=1,opacity:i=1,scale:o=1,size:s,color:c,children:n,...h},m)=>{y.useMemo(()=>bt({SparklesImplMaterial:gt}),[]);let l=y.useRef(null),p=N(d=>d.viewport.dpr),u=Vt(o),g=y.useMemo(()=>Float32Array.from(Array.from({length:t},()=>u.map(Z.randFloatSpread)).flat()),[t,...u]),f=$(t,s,Math.random),_=$(t,i),S=$(t,e),A=$(t*3,r),I=$(c===void 0?t*3:t,It(c)?c:new b(c),()=>1);return P(d=>{l.current&&l.current.material&&(l.current.material.time=d.clock.elapsedTime)}),y.useImperativeHandle(m,()=>l.current,[]),y.createElement("points",V({key:`particle-${t}-${JSON.stringify(o)}`},h,{ref:l}),y.createElement("bufferGeometry",null,y.createElement("bufferAttribute",{attach:"attributes-position",args:[g,3]}),y.createElement("bufferAttribute",{attach:"attributes-size",args:[f,1]}),y.createElement("bufferAttribute",{attach:"attributes-opacity",args:[_,1]}),y.createElement("bufferAttribute",{attach:"attributes-speed",args:[S,1]}),y.createElement("bufferAttribute",{attach:"attributes-color",args:[I,3]}),y.createElement("bufferAttribute",{attach:"attributes-noise",args:[A,3]})),n||y.createElement("sparklesImplMaterial",{transparent:!0,pixelRatio:p,depthWrite:!1}))});function Wt({mode:r}){let t=N(e=>e.invalidate);return(0,a.useEffect)(()=>{if(t(),r==="bal"){let e=setInterval(t,41.666666666666664);return()=>clearInterval(e)}if(r==="eco"){let e=setTimeout(t,700);return()=>clearTimeout(e)}},[r]),null}var kt=`
vec3 mod289(vec3 x){return x-floor(x*(1./289.))*289.;} vec4 mod289(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 perm(vec4 x){return mod289(((x*34.)+1.)*x);} vec4 tis(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){const vec2 C=vec2(1./6.,1./3.);const vec4 D=vec4(0.,.5,1.,2.);vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;i=mod289(i);vec4 p=perm(perm(perm(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));float n_=.142857142857;vec3 ns=n_*D.wyz-D.xzx;vec4 j=p-49.*floor(p*ns.z*ns.z);vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.*x_);vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.-abs(x)-abs(y);vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);vec4 s0=floor(b0)*2.+1.;vec4 s1=floor(b1)*2.+1.;vec4 sh=-step(h,vec4(0.));vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);vec4 nm=tis(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));p0*=nm.x;p1*=nm.y;p2*=nm.z;p3*=nm.w;vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);m=m*m;return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));}
float fbm(vec3 p){float a=.5,s=0.;for(int i=0;i<4;i++){s+=a*snoise(p);p=p*2.03+vec3(1.7,9.2,3.1);a*=.5;}return s;}`,Xt=`varying vec3 vP; varying vec3 vN; varying vec3 vV; uniform float uT;
${kt}
void main(){ vP=position; vN=normalize(normalMatrix*normal); float d=fbm(position*1.6+vec3(0.,uT*.12,0.))*.06; vec3 p=position+normal*d; vec4 mv=modelViewMatrix*vec4(p,1.); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }`,qt=`varying vec3 vP; varying vec3 vN; varying vec3 vV; uniform float uT; uniform float uBoost; uniform float uDeep;
${kt}
void main(){
  vec3 q=normalize(vP);
  float n=fbm(q*2.2+vec3(uT*.10,-uT*.07,uT*.05));
  float m=fbm(q*5.0+vec3(-uT*.18,uT*.11,0.));
  float h=clamp(.55+n*.9+m*.28,0.,1.);
  float fr=pow(1.-max(dot(normalize(vN),normalize(vV)),0.),2.2);
  vec3 red=vec3(.28,.02,.01), org=vec3(1.,.36,.03), amb=vec3(1.,.66,.18), hot=vec3(1.,.86,.5);
  vec3 c=mix(red,org,smoothstep(.0,.45,h)); c=mix(c,amb,smoothstep(.4,.8,h)); c=mix(c,hot,smoothstep(.8,1.,h)*.7);
  c=mix(c,red*1.2,smoothstep(.35,1.,fr));
  gl_FragColor=vec4(c*(0.95+uBoost*.4),1.);
}`,Qt="varying vec3 vN; varying vec3 vV; void main(){ vN=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }",$t=`varying vec3 vN; varying vec3 vV; uniform float uBoost;
void main(){ float f=pow(max(dot(normalize(vN),normalize(vV)),0.),2.6); vec3 c=mix(vec3(.55,.06,.0),vec3(1.,.45,.05),f); gl_FragColor=vec4(c,f*(.75+uBoost*.25)); }`;function Jt({busy:r,quiet:t,sunRef:e,glow:i,deep:o=!1}){let s=(0,a.useMemo)(()=>new z({uniforms:{uT:{value:0},uBoost:{value:0},uDeep:{value:0}},vertexShader:Xt,fragmentShader:qt}),[]),c=(0,a.useMemo)(()=>new z({uniforms:{uBoost:{value:0}},vertexShader:Qt,fragmentShader:$t,transparent:!0,side:Et,depthWrite:!1,blending:J}),[]),n=(0,a.useRef)(),h=(0,a.useRef)(1);return P((m,l)=>{let p=t?.15:r?2.2:1;if(h.current+=(p-h.current)*Math.min(1,l*3),s.uniforms.uDeep.value=o?1:0,s.uniforms.uT.value+=l*h.current,s.uniforms.uBoost.value=r?1:0,c.uniforms.uBoost.value=r?1:0,n.current){n.current.rotation.y+=l*.05*h.current;let u=r?1+.03*Math.sin(m.clock.elapsedTime*6):1+.012*Math.sin(m.clock.elapsedTime*1.2);n.current.scale.setScalar(u)}}),a.default.createElement("group",null,a.default.createElement("mesh",{ref:n,material:s},a.default.createElement("sphereGeometry",{args:[1,96,96]})),i&&a.default.createElement("mesh",{ref:e,scale:1},a.default.createElement("sphereGeometry",{args:[1,32,32]}),a.default.createElement("meshBasicMaterial",{color:"#ff7a10",transparent:!0,opacity:0,depthWrite:!1})),a.default.createElement("mesh",{scale:1.32,material:c},a.default.createElement("sphereGeometry",{args:[1,48,48]})),a.default.createElement("pointLight",{color:"#ff8a1a",intensity:30,distance:10}))}var te=[[1.15,.2,0],[.35,.9,.5],[-.5,.1,1.2]],ee=[1.9,2.3,2.7];function oe({r,i:t,speed:e,mini:i}){let o=(0,a.useRef)(),s=(0,a.useRef)(),{pts:c,cols:n}=(0,a.useMemo)(()=>{let h=[],m=[],l=new b("#ffb454"),p=new b("#ff5a0a"),u=new b("#5a1405");for(let g=0;g<=180;g++){let f=g/180*Math.PI*2;h.push([Math.cos(f)*r,0,Math.sin(f)*r]);let _=(Math.sin(f*1+t)+1)/2;m.push((_>.5?l.clone().lerp(p,(_-.5)*2):u.clone().lerp(l,_*2)).toArray())}return{pts:h,cols:m}},[r,t]);return P((h,m)=>{s.current&&(s.current.rotation.y+=m*.05*(t+1));let l=h.clock.elapsedTime*e+t*2.1;o.current&&o.current.position.set(Math.cos(l)*r,0,Math.sin(l)*r)}),a.default.createElement("group",{rotation:te[t]},a.default.createElement("group",{ref:s},a.default.createElement(dt,{points:c,vertexColors:n,lineWidth:i?.8:1.1,transparent:!0,opacity:.55,toneMapped:!1,dashed:t===1,dashSize:.12,gapSize:.08}),a.default.createElement("mesh",{ref:o},a.default.createElement("sphereGeometry",{args:[.055,16,16]}),a.default.createElement("meshBasicMaterial",{color:t===1?"#ff7a1a":"#ffb454",toneMapped:!1}))))}function re({quiet:r,busy:t,mini:e,hero:i,center:o,sunRef:s,glow:c}){let n=N(f=>f.size),h=i?Math.min(1,n.width/420,n.height/300):e?1:Math.min(1,n.width/520),m=(0,a.useRef)();P(f=>{if(!e){let _=f.pointer.x*(i?.9:.5),S=f.pointer.y*(i?.5:.3);f.camera.position.x+=(_-f.camera.position.x)*.04,f.camera.position.y+=(S-f.camera.position.y)*.04,f.camera.lookAt(0,0,0)}});let l=n.width/n.height,p=l>1.3,u=o?p?1.55:.8:i?p?Math.min(1,n.height/560)*.8:.55:e?.9:.42*h,g=o?p?0:1.5:i?p?0:.85:e?0:1.75+(1-h)*.9;return a.default.createElement(ft,{speed:r?.3:1.2,rotationIntensity:.1,floatIntensity:e?0:.3},a.default.createElement("group",{position:[i&&p&&!o?1.05*l:0,g,0],scale:u},a.default.createElement("group",{scale:i?1.35:1},a.default.createElement(Jt,{busy:t,quiet:r,sunRef:s,glow:c})),ee.slice(0,e?2:3).map((f,_)=>a.default.createElement("group",{key:_,rotation:[0,0,0]},a.default.createElement(oe,{r:f,i:_,speed:.45+_*.2,mini:e})))))}function ie({mode:r="max",quiet:t=!1,busy:e=!1,drawing:i=!1,mini:o=!1,hero:s=!1,center:c=!1}){let[n,h]=(0,a.useState)(null),m=r==="max"?[1,1.5]:1,l=r!=="eco"&&!o,p=l&&r==="max";return a.default.createElement(Mt,{onCreated:({gl:u})=>{o&&u.setClearColor(0,0)},frameloop:r==="max"?"always":"demand",dpr:m,camera:{position:[0,0,o?6.2:8.5],fov:40},gl:{antialias:!l,alpha:o,powerPreference:"high-performance",toneMapping:vt,toneMappingExposure:1}},!o&&a.default.createElement("color",{attach:"background",args:["#000000"]}),a.default.createElement(Wt,{mode:r}),!o&&a.default.createElement(_t,{radius:30,depth:40,count:r==="eco"?700:1800,factor:3.2,saturation:0,fade:!0,speed:t?.2:1}),!o&&r!=="eco"&&a.default.createElement(yt,{count:r==="max"?70:30,scale:[7,4.5,4],size:1.6,speed:t?.05:.4,opacity:.8,color:"#ffb454"}),a.default.createElement(re,{quiet:t,busy:e,mini:o,hero:s,center:c,glow:p,sunRef:h}),l&&a.default.createElement(Pt,{multisampling:0},n&&p?a.default.createElement(wt,{sun:n,samples:28,density:.85,decay:.92,weight:.22,exposure:.28,clampMax:.8,blur:!0}):a.default.createElement(a.default.Fragment,null),a.default.createElement(Ut,{mipmapBlur:!0,luminanceThreshold:.55,luminanceSmoothing:.25,intensity:r==="max"?.9:.65})))}export{Jt as Sun,ie as default};
/*! Bundled license information:

camera-controls/dist/camera-controls.module.js:
  (*!
   * camera-controls
   * https://github.com/yomotsu/camera-controls
   * (c) 2017 @yomotsu
   * Released under the MIT License.
   *)
*/
