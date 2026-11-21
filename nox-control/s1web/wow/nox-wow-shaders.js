/* Шейдеры туманности и звёзд HYG - из nox-v14-real.js (тот же вид), для единого WebGL-контекста three. */
export const VS='#version 300 es\nin vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
export const NEB='#version 300 es\nprecision highp float;uniform vec2 uRes;uniform float uT;out vec4 o;'+
'float h(vec2 p){p=fract(p*vec2(.1031,.1030));p+=dot(p,p.yx+33.33);return fract((p.x+p.y)*p.x);}'+
'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}'+
'float fbm(vec2 p){float a=.5,s=0.;mat2 R=mat2(.8,-.6,.6,.8);for(int i=0;i<5;i++){s+=a*n(p);p=R*p*2.03+11.7;a*=.5;}return s;}'+
'float fb2(vec2 p){return .6*n(p)+.4*n(p*2.1+3.7);}'+
'void main(){vec2 uv=gl_FragCoord.xy/uRes;vec2 p=(uv-.5)*vec2(uRes.x/uRes.y,1.)*2.4;float t=uT*.010;'+
'vec2 q=vec2(fbm(p+vec2(0.,t)),fbm(p+vec2(5.2,1.3)-t));'+
'vec2 r=vec2(fbm(p+3.2*q+vec2(1.7,9.2)+t*.7),fbm(p+3.2*q+vec2(8.3,2.8)-t*.5));'+
'float f=fbm(p+3.4*r);'+
'float dens=pow(smoothstep(.36,.92,f),2.2)*(.35+.65*q.x);'+
'float d=fbm(vec2(p.x*1.0+q.y*1.6,p.y*3.4+q.x*1.6)+7.);float dust=smoothstep(.46,.78,d);float tr=exp(-3.0*dust*dust);'+
'vec3 ha=vec3(.55,.05,.11),ha2=vec3(.92,.28,.33),bl=vec3(.09,.23,.52),ox=vec3(.04,.30,.36);'+
'vec3 col=mix(ha,ha2,smoothstep(.5,.98,f))*dens*.55;'+
'col+=bl*pow(smoothstep(.5,.95,r.y),2.)*(1.-dens)*.30;col+=ox*smoothstep(.65,1.,q.y)*.10*dens;'+
'vec2 L=vec2(.68,.80);vec2 st=(L-uv)/8.;float sh=0.,tt=1.;vec2 pp=uv;for(int i=0;i<8;i++){pp+=st;float dd=fb2(pp*vec2(uRes.x/uRes.y,1.)*3.+q*2.+t*3.);tt*=1.-.11*smoothstep(.45,.85,dd);sh+=tt;}'+
'sh/=8.;float lf=1.-smoothstep(0.,.95,length(uv-L));col+=vec3(1.,.55,.42)*sh*lf*lf*.035;'+
'col*=tr;col*=.92+.08*sin(uT*.05);col+=vec3(.003,.005,.011);'+
'o=vec4(col,1.);}';
export const COMP='#version 300 es\nprecision highp float;uniform sampler2D uN;uniform vec2 uPar;uniform float uExp;uniform vec2 uRes;out vec4 o;'+
'vec3 aces(vec3 x){return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14),0.,1.);}'+
'void main(){vec2 uv=gl_FragCoord.xy/uRes;vec3 c=texture(uN,uv*.96+.02+uPar).rgb*uExp;c=aces(c);float l=dot(c,vec3(.2126,.7152,.0722));c=mix(vec3(l),c,.82);o=vec4(c,1.);}';
export const SVS='#version 300 es\nin vec4 aS;in vec3 aC;uniform vec2 uRes;uniform float uDpr,uRa,uTime;uniform vec2 uPar;out vec3 vC;out float vK;out float vI;\n'+
'void main(){float ra=radians(aS.x)+uRa,de=radians(aS.y);float ra0=radians(83.),d0=radians(4.);float c0=cos(d0),s0=sin(d0);float dl=ra-ra0;dl=atan(sin(dl),cos(dl));'+
'float cc=s0*sin(de)+c0*cos(de)*cos(dl);if(cc<-.9){gl_Position=vec4(2.,2.,2.,1.);gl_PointSize=0.;return;}float k=2./(1.+cc);float x=-k*cos(de)*sin(dl);float y=k*(c0*sin(de)-s0*cos(de)*cos(dl));'+
'float s=max(uRes.x,uRes.y)*.5/1.2;vec2 px=vec2(x,y)*s;gl_Position=vec4(px.x/(uRes.x*.5)+uPar.x*2.,px.y/(uRes.y*.5)+uPar.y*2.,0.,1.);'+
'float b=pow(10.,-.4*(aS.z-6.));float sp=smoothstep(12.,160.,b);float core=uDpr*(1.1+1.15*log2(1.+b));float size=core+sp*uDpr*34.;gl_PointSize=min(size,64.*uDpr);'+
'vK=core/max(gl_PointSize,1.);vI=min(.16+.62*log(1.+b)/log(10.),1.6);vC=aC*(vec3(1.)+sp*.4);'+
'float ph=fract(sin(float(gl_VertexID)*12.9898)*43758.5453)*6.28;float tw=1.+.07*sin(uTime*(1.3+fract(ph)*2.)+ph);vI*=tw;vK=vK;}';
export const SFS='#version 300 es\nprecision highp float;in vec3 vC;in float vK;in float vI;out vec4 o;\n'+
'void main(){vec2 c=gl_PointCoord*2.-1.;float r=length(c);float kk=max(vK,.05);float core=exp(-pow(r/kk,2.)*2.6);'+
'float sp=exp(-abs(c.x)*55.)*exp(-abs(c.y)*3.2)+exp(-abs(c.y)*55.)*exp(-abs(c.x)*3.2);float spk=sp*step(.0,.5-kk)*.55;'+
'float a=(core+spk)*vI;o=vec4(vC*a,1.);}';
