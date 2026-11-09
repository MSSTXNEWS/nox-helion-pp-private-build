import {radiantCorona} from './radiant-corona.mjs';
// NOX canonical planet and corona materials. Object-space terrain anchors the
// graphite crust; the shared owner clock advects heat beneath it, without textures.
// Lava advection adapts the two independently drifting, noise-distorted channels
// of three.js r160 webgl_shader_lava (Three.js authors / TheGameMaker, MIT).
// Pinned original and license: vendor/licenses/three-lava/{source.json,LICENSE}.
const noise = /* glsl */`
float hash3(vec3 p) {
  p = fract(p * .1031); p += dot(p, p.yzx + 33.33);
  return fract((p.x + p.y) * p.z);
}
float grain(vec3 p) {
  vec3 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(mix(hash3(i),hash3(i+vec3(1,0,0)),f.x),mix(hash3(i+vec3(0,1,0)),hash3(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hash3(i+vec3(0,0,1)),hash3(i+vec3(1,0,1)),f.x),mix(hash3(i+vec3(0,1,1)),hash3(i+vec3(1)),f.x),f.y),f.z);
}
float terrain(vec3 p) {
  return grain(p)*.53+grain(p*2.03+4.7)*.26+grain(p*4.11-2.4)*.14+grain(p*8.25+1.8)*.07;
}`;
const paletteUniforms = /* glsl */`
uniform vec3 uPaletteColor; uniform float uPaletteMix;
vec3 paletteEmission(vec3 light){float peak=max(light.r,max(light.g,light.b));return mix(light,uPaletteColor*peak,uPaletteMix);}
`;
const mappedMetalUniforms = /* glsl */`
uniform sampler2D uBaseMap,uNormalMap,uRoughnessMap,uMetalnessMap,uEnvironmentMap;
uniform float uPbrReady,uEnvironmentReady,uEnvironmentIntensity,uClassicBlackSun;
uniform vec3 uMaterialTint;
vec3 mapLinear(vec3 c){return mix(c/12.92,pow((c+.055)/1.055,vec3(2.4)),step(vec3(.04045),c));}
vec3 environmentAt(vec3 direction){vec3 d=normalize(direction);vec2 uv=vec2(atan(d.z,d.x)*.159154943+.5,asin(clamp(d.y,-1.,1.))*.318309886+.5);return texture2D(uEnvironmentMap,uv).rgb;}
`;
export const planetVertex = /* glsl */`
varying vec3 vPoint; varying vec3 vNormal; varying vec3 vTangent; varying vec3 vView; varying vec2 vMaterialUv;
void main(){
 vPoint=position; vNormal=normalize(normalMatrix*normal); vMaterialUv=uv;
 vec3 axis=abs(normal.y)>.92?vec3(0.,0.,1.):vec3(0.,1.,0.);
 vTangent=normalize(normalMatrix*normalize(cross(axis,normal)));
 vec4 viewPosition=modelViewMatrix*vec4(position,1.);
 vView=-viewPosition.xyz; gl_Position=projectionMatrix*viewPosition; }`;
export const planetFragment = /* glsl */`
varying vec3 vPoint; varying vec3 vNormal; varying vec3 vTangent; varying vec3 vView; varying vec2 vMaterialUv;
uniform float clockTime; uniform float activity;
${paletteUniforms}
${mappedMetalUniforms}
${noise}
void main(){
 vec3 p=vPoint*inversesqrt(max(dot(vPoint,vPoint),.00001));
 vec3 n=vNormal*inversesqrt(max(dot(vNormal,vNormal),.00001));
 float energy=clamp(activity,0.,1.);
 float crust=terrain(p*5.6+vec3(7.,3.,8.));
 float layer=terrain(p*18.+2.7*crust); float fine=grain(p*125.);
 float fractured=abs(layer-.48+sin(crust*14.)*.055);
 float fissure=1.-smoothstep(.003,.015,fractured);
 // Two r160-style advected channels, sampled procedurally on the sphere rather
 // than from image UVs. The fixed crust masks continuous flow inside fissures.
 // Only two single-octave samples are added; no extra FBM, passes or geometry.
 vec3 flowA=p*8.+vec3(1.5,-1.5,.43)*clockTime*.02;
 vec3 flowB=p*11.+vec3(-.5,2.,-.35)*clockTime*.01;
 flowA+=vec3(crust,layer,fine)*2.;
 flowB+=vec3(-layer,crust,-fine)*.2;
 float advectA=grain(flowA*2.),advectB=grain(flowB*2.);
 float heat=smoothstep(.22,.83,advectA*.72+advectB*.42);
 float channel=1.-smoothstep(.012,.075,fractured);
 float height=crust*.6+layer*.3+fine*.1+(advectA-.5)*channel*.025;
 vec3 perturbed=normalize(n+vec3(-dFdx(height),-dFdy(height),0.)*2.1);
 vec2 mapUv=vMaterialUv*vec2(3.,2.);float measuredRoughness=.5,measuredMetalness=1.;vec3 mappedBase=vec3(0.);
 if(uPbrReady>.5){
  measuredRoughness=clamp(texture2D(uRoughnessMap,mapUv).r,.08,.98);
  measuredMetalness=texture2D(uMetalnessMap,mapUv).r;
  mappedBase=mapLinear(texture2D(uBaseMap,mapUv).rgb)*uMaterialTint;
  vec3 mapNormal=texture2D(uNormalMap,mapUv).xyz*2.-1.;mapNormal.xy*=.32;
  vec3 mapTangent=normalize(vTangent-perturbed*dot(vTangent,perturbed));
  perturbed=normalize(mapTangent*mapNormal.x+cross(perturbed,mapTangent)*mapNormal.y+perturbed*max(.1,mapNormal.z));
 }
 vec3 view=vView*inversesqrt(max(dot(vView,vView),.00001));
 vec3 key=normalize(vec3(.52,.79,.34)),halfway=normalize(key+view);
 vec3 tangent=vTangent-perturbed*dot(vTangent,perturbed);
 tangent*=inversesqrt(max(dot(tangent,tangent),.00001));
 vec3 bitangent=cross(perturbed,tangent);
 bitangent*=inversesqrt(max(dot(bitangent,bitangent),.00001));
 float light=max(dot(perturbed,key),0.),viewFacing=clamp(dot(perturbed,view),0.,1.);
 float rim=pow(1.-viewFacing,2.9);
 float glint=pow(light,4.6)*(.15+.85*layer)*(.15+.85*crust);
 // Fine mineral lamination shares the terrain field: no extra FBM or texture.
 float lamina=.5+.5*sin(layer*113.+crust*41.+fine*2.2);
 float bevel=pow(clamp(1.-abs(layer-crust)*2.,0.,1.),7.);
 float strata=smoothstep(.24,.72,crust+layer*.2)*pow(light,2.7);
 float seam=1.-smoothstep(.015,.055,abs(fract(layer*2.7+crust)-.5));
 // Bounded anisotropic microfacet lobe: long graphite laminae catch the light
 // according to both view and tangent, rather than a camera-independent glow.
 float alphaT=mix(.13+.065*layer,.08+measuredRoughness*.38,uPbrReady),alphaB=mix(.36+.1*crust,.17+measuredRoughness*.57,uPbrReady);
 float hT=dot(halfway,tangent)/alphaT,hB=dot(halfway,bitangent)/alphaB;
 float hN=max(dot(halfway,perturbed),0.);
 float lobeDenom=max(hT*hT+hB*hB+hN*hN,.0001);
 float metalLobe=min(12.,1./(3.14159265*alphaT*alphaB*lobeDenom*lobeDenom));
 float grazing=pow(1.-clamp(dot(view,halfway),0.,1.),5.);
 vec3 fresnel=mix(vec3(.13,.145,.16),vec3(.68,.66,.62),grazing);
 vec3 color=mix(vec3(.003,.004,.0055),vec3(.026,.029,.033),crust)*(.29+light);
 if(uPbrReady>.5)color=color*.65+mappedBase*(.012+.045*light);
 if(uEnvironmentReady>.5){
  vec3 reflected=reflect(-view,perturbed);float blur=.025+measuredRoughness*.24;
  vec3 environment=environmentAt(reflected)*.5+environmentAt(reflected+tangent*blur)*.25+environmentAt(reflected-bitangent*blur)*.25;
  environment/=1.+max(environment.r,max(environment.g,environment.b))*.15;
  color+=environment*fresnel*(.25+.75*measuredMetalness)*uEnvironmentIntensity*(.42+.58*(1.-measuredRoughness));
 }
 color+=fresnel*metalLobe*light*(.13+.065*lamina)*(.62+.38*bevel);
 color+=vec3(.15,.145,.14)*glint*(.65+fine);
 color+=vec3(.11,.108,.10)*strata*(.3+.85*fine)*(1.-.4*seam);
 color+=vec3(.11,.072,.045)*rim*(.2+.8*crust);
 // Obsidian ridges and a very restrained thin-film tint, confined to the limb.
 vec3 film=.5+.5*cos(vec3(0.,1.6,3.2)+layer*9.+crust*5.+(1.-viewFacing)*11.);
 color+=film*vec3(.032,.026,.025)*metalLobe*light*bevel*(.22+.48*(1.-viewFacing));
 color+=mix(vec3(.15,.078,.025),film*vec3(.085,.058,.049),.34)*rim*bevel;
 color+=vec3(.12,.10,.072)*glint*lamina*bevel*.48;
 float edgeThread=smoothstep(.80,.99,lamina)*rim*seam;
 color+=vec3(.62,.24,.044)*edgeThread*(.19+.13*energy);
 // Classic black sun dims the solid metal only; molten advection and solar emission remain intact.
 color=mix(color,color*vec3(.12,.10,.075),uClassicBlackSun);
 // Camera-facing core should read as an obsidian eclipse, not a lit grey planet.
 // Preserve microstructure and molten fissures while attenuating solid-surface exposure.
 color*=vec3(.39,.355,.315);
 float lavaFlow=.35+.95*heat;
 float molten=fissure*lavaFlow*smoothstep(.32,.70,crust);
 color+=paletteEmission(vec3(.69,.32,.12))*molten*(.035+.45*rim+.10*light)*(.62+.12*energy);
 color+=paletteEmission(vec3(.10,.064,.037))*channel*heat*(.12+.12*light);
 color+=paletteEmission(vec3(.16,.097,.046))*fissure*energy*(.22+.13*advectB);
 // Heat-fracture pearlescence: a narrow mineral film, not a second light source.
 float pearl=fissure*bevel*(.18+.82*rim)*smoothstep(.48,.79,crust);
 vec3 pearlTint=mix(vec3(.19,.11,.045),vec3(.043,.065,.067),film.g*.26);
 color+=pearlTint*pearl*lavaFlow*.36;
 gl_FragColor=vec4(clamp(color,vec3(0.),vec3(8.)),1.);
}`;
export const skyVertex = /* glsl */`
varying vec2 vUv;
void main(){vUv=uv; gl_Position=vec4(position.xy,0.,1.);}`;
export const skyFragment = /* glsl */`
varying vec2 vUv; uniform vec2 span; uniform vec2 center; uniform float clockTime; uniform float activity;
uniform sampler2D uBackgroundMap; uniform float uBackgroundMix;
${noise}
${paletteUniforms}
${radiantCorona}
vec3 starField(vec2 p,float scale,float depth,float t) {
 vec2 cell=p*scale, id=floor(cell), f=fract(cell)-.5;
 float h=hash3(vec3(id,depth)); if(h<.905)return vec3(0.);
 // A coarse density field breaks the uniform star grid; calculate it only in
 // candidate cells. Position, size, temperature and brightness are independent.
 float cluster=grain(vec3(id*.095,depth*.17));
 if(h<.935+(.5-cluster)*.045)return vec3(0.);
 vec2 star=vec2(hash3(vec3(id,depth+3.)),hash3(vec3(id,depth+8.)))*.72-.36;
 vec2 delta=f-star; float d=length(delta);
 float size=mix(.017,.069,pow(hash3(vec3(id,depth+13.)),3.));
 float aa=max(size*.42,.004);
 float core=1.-smoothstep(size-aa,size+aa,d);
 float halo=exp(-d*d/max(size*size*4.,.0001))*.12;
 float brightness=.12+1.45*pow(hash3(vec3(id,depth+19.)),4.);
 float temperature=hash3(vec3(id,depth+29.));
 vec3 tint=mix(vec3(.69,.79,1.),vec3(1.,.79,.54),temperature);
 // Slow, tiny independent scintillation, never a synchronized screen blink.
 float quiet=1.+.025*sin(t*.021+hash3(vec3(id,depth+41.))*6.2831853);
 return tint*(core+halo)*brightness*quiet;
}
void main(){
 vec2 p=(vUv-center)*span; float radius=length(p), t=clockTime;
 float energy=clamp(activity,0.,1.);
 // The opaque planet fully covers these pixels; skip expensive corona/noise work.
#ifndef NOX_STARFIELD_ONLY
 if(radius<.985){gl_FragColor=vec4(0.,0.,0.,1.);return;}
#endif
 float smoke=terrain(vec3(p*1.2+vec2(t*.00032,-t*.00019),2.));
 float dust=pow(terrain(vec3(p*2.7+2.2*smoke+vec2(-t*.00024,t*.00013),3.)),3.);
 float lane=exp(-pow(abs((p.y+.42+.32*sin(p.x*1.2))*2.2),2.));
 vec3 sky=vec3(.0014,.0020,.0031)+vec3(.018,.016,.015)*dust*lane;
 vec3 stars=starField(p+vec2(t*.00017,-t*.0001),31.,1.,t)*.35;
 stars+=starField(p*.79+vec2(-t*.00052,t*.00028)+41.,19.,29.,t)*.38;
 sky+=stars;
 // Two depth planes: slow foreground motes against the existing fixed stars.
 // The shared clock is frozen by Reduced Motion/input/visibility policy upstream.
 vec3 motes=starField(p*.53+vec2(t*.00145,-t*.00086),11.,61.,t);
 float parallaxVeil=lane*(.18+.82*smoke);
 sky+=motes*(.42+.58*parallaxVeil)*.15;
 sky+=vec3(.0025,.002,.0014)*dust*parallaxVeil;
 // Existing dust fields form a second, quieter depth layer without more noise.
 float distantVeil=exp(-pow(abs((p.y-.15+.17*sin(p.x*.7))*1.8),2.));
 sky+=vec3(.0013,.0011,.0009)*dust*smoke*distantVeil;
 // Only the distant sky changes. The original opaque planet, corona and its
 // reflection below are kept intact; classic takes the original branch exactly.
 if(uBackgroundMix>.5){sky=min(texture2D(uBackgroundMap,vUv).rgb,vec3(.17))*.33;if(uBackgroundMix>1.5)sky+=stars*.25;}
#ifdef NOX_STARFIELD_ONLY
 // Global contextual pages reuse the same scene/clock but have no eclipse hole,
 // corona, ocean reflection, planet or second renderer.
 gl_FragColor=vec4(clamp(sky,vec3(0.),vec3(8.)),1.);return;
#endif
 vec2 ray=p/max(radius,.0001);float angle=atan(ray.y,ray.x);
 float radial=max(0.,radius-1.);
 float plasmaAngle=angle+.065*sin(radial*8.-t*.11+angle*3.)+.018*sin(angle*7.-t*.037);
 vec2 flowRay=vec2(cos(plasmaAngle),sin(plasmaAngle));
 float gran=grain(vec3(flowRay*37.+vec2(radial*9.,-radial*6.),t*.10));
 float curl=terrain(vec3(flowRay*7.7+vec2(radial*1.3,-radial*.7),t*.08+5.));
 float strands=pow(grain(vec3(flowRay*78.+curl*3.5+vec2(radial*17.,-radial*11.),t*.17)),2.);
 float fork=pow(grain(vec3(flowRay*21.+vec2(radial)*.75,t*.11)),4.);
 float reach=max(.006,.008+.014*curl+.031*strands+.038*fork);
 // Independent slow phase velocities break the mechanical uniform corona pulse.
 float filamentPhase=angle*39.+curl*19.-radial*31.+t*(.065+.045*gran);
 float filament=pow(clamp(.5+.5*sin(filamentPhase),0.,1.),15.);
 float knot=pow(clamp(.5+.5*sin(angle*13.-radial*22.-t*.047+fork*7.),0.,1.),10.);
 float braid=filament*exp(-radial*(14.+18.*strands))*(.14+.52*fork);
 float rim=exp(-radial*(118.-38.*gran))*(1.8+1.1*gran);
 float rays=exp(-radial/reach)*(.09+.81*strands+.55*fork);
 float flare=pow(.5+.5*sin(angle*21.+curl*16.-radial*16.+t*.12),9.)*exp(-radial*10.)*.36;
 vec3 corona=vec3(.43,.18,.047)*rays+vec3(.83,.44,.20)*rim+vec3(.38,.21,.09)*flare;
 corona+=mix(vec3(.74,.19,.024),vec3(1.30,.67,.23),gran)*braid;
 corona+=vec3(.67,.24,.042)*knot*fork*exp(-radial*18.)*.24;
 float archRadius=.035+.055*fork+.018*sin(angle*5.-t*.043);
 float arch=exp(-pow((radial-archRadius)*54.,2.))*filament*fork;
 corona+=vec3(.78,.29,.061)*arch*.19;
 // A dim mineral sheen remains local to the edge, never a full-field rainbow.
 corona+=vec3(.038,.057,.063)*rim*strands*(.5+.5*sin(angle*5.+curl*8.))*.12;
 float breath=.94+.04*sin(t*.071)+.02*sin(t*.113+angle*3.);
 // Subtle anamorphic scattering remains local to the illuminated limb.
 vec2 opticalAxis=vec2(.86,.51);
 float axial=dot(p,opticalAxis),crossAxis=dot(p,vec2(-opticalAxis.y,opticalAxis.x));
 float halo=exp(-radial*5.6)*pow(abs(dot(ray,opticalAxis)),8.);
 sky+=vec3(.027,.013,.004)*halo*smoothstep(1.,1.025,radius);
 // Rare shallow lens ghosts share the same clock; no extra geometry or layers.
 float rare=pow(clamp(.5+.5*sin(t*.017+1.4),0.,1.),18.);
 float ghostA=exp(-pow(abs((axial+1.62)*13.),2.)-pow(abs(crossAxis*28.),2.));
 float ghostB=exp(-pow(abs((axial-1.86)*17.),2.)-pow(abs((crossAxis-.025)*34.),2.));
 sky+=vec3(.030,.019,.008)*(ghostA+ghostB*.45)*rare*smoothstep(1.15,1.35,radius);
 sky+=paletteEmission(corona*breath + radiant(p,t)*.045*exp(-radial*7.))*(.57+energy*.14)*smoothstep(.987,1.,radius);
 float below=max(0.,-p.y-.998);
 if(p.y<-.998 && false){
   float wave=grain(vec3(p.x*7.,below*43.+t*.3,2.))+grain(vec3(p.x*23.,below*93.-t*.27,9.))*.3;
   float band=exp(-below*6.5);
   float strike=exp(-abs(p.x)*(.9+12.*band));
   sky=mix(vec3(.002,.002,.003)+.006*sky,paletteEmission(vec3(.62,.24,.042)),band*strike*(.2+wave));
   sky+=paletteEmission(vec3(1.4,.57,.08))*exp(-below*145.)*exp(-abs(p.x)*2.8);
   sky+=paletteEmission(vec3(.97,.38,.08))*exp(-abs(p.x)*5.)*exp(-below*7.)*smoothstep(.46,.83,wave);
 }
 gl_FragColor=vec4(clamp(sky,vec3(0.),vec3(8.)),1.);
}`;
