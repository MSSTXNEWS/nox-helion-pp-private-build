"""NOX Creative Studio additive integrations: projects, 3D, voice, chat.

No network endpoint or model is implied by this file. 3D is explicitly
procedural; 2D/photo/video AI generation uses installed ComfyUI workflows.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

MEDIA_SUFFIXES = {'.mp4','.mov','.mkv','.webm','.png','.jpg','.jpeg','.webp',
                  '.wav','.mp3','.flac','.ogg','.srt','.glb','.gltf','.obj','.json'}
MAX_UPLOAD = 256 * 1024 * 1024
CREATION_VERBS = ('создай','создать','сделай','сделать','сгенерируй','сгенерировать',
                  'подготовь','построй','create ','generate ','make ','build ')

class CreativeExtensions:
    def project_files(self, project_id):
        folder = self._project(project_id)
        output=[]
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or '_normalized' in path.relative_to(folder).parts:
                continue
            if path.suffix.lower() in MEDIA_SUFFIXES or path.name=='storyboard.json':
                output.append({'path':path.relative_to(folder).as_posix(),
                               'bytes':path.stat().st_size,
                               'sha256':hashlib.sha256(path.read_bytes()).hexdigest()
                               if path.stat().st_size<32_000_000 else None})
        return {'status':'OK','project_id':project_id,'files':output}

    def upload(self,project_id,filename,source,length):
        from .engine import StudioError
        if not isinstance(length,int) or length<1 or length>MAX_UPLOAD:
            raise StudioError('Upload must contain 1..256 MiB')
        if not re.fullmatch(r'[\w .()\-]{1,128}',filename,re.UNICODE):
            raise StudioError('Invalid asset filename')
        suffix=Path(filename).suffix.lower()
        if suffix not in MEDIA_SUFFIXES:raise StudioError('Unsupported project asset extension')
        folder=self._project(project_id)/'assets';folder.mkdir(parents=True,exist_ok=True)
        safe=uuid.uuid4().hex[:10]+'_'+filename.replace(' ','_')
        tmp=folder/(safe+'.partial');output=folder/safe
        digest=hashlib.sha256();remaining=length
        try:
            with tmp.open('xb') as f:
                while remaining:
                    chunk=source.read(min(1024*1024,remaining))
                    if not chunk:raise StudioError('Incomplete asset upload')
                    remaining-=len(chunk);digest.update(chunk);f.write(chunk)
            tmp.replace(output)
        finally:
            if tmp.exists():tmp.unlink()
        return {'status':'IMPORTED','project_id':project_id,
                'path':'assets/'+safe,'bytes':length,'sha256':digest.hexdigest()}

    def make_3d(self,project_id='',form='sphere',color='#b9753c'):
        """Real GLB mesh creation from safe procedural shapes, NOT diffusion AI."""
        from .engine import StudioError
        try:import trimesh
        except ImportError as exc:raise StudioError('Install optional trimesh to create procedural GLB') from exc
        if form not in ('sphere','cube','torus','capsule','icosphere','cone','cylinder'):
            raise StudioError('Unsupported 3D shape')
        if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
            raise StudioError('Color must be #RRGGBB')
        pid=project_id or uuid.uuid4().hex[:12];folder=self._project(pid)
        shapes={
          'sphere':lambda:trimesh.creation.uv_sphere(radius=1, count=[24,48]),
          'cube':lambda:trimesh.creation.box(extents=[1.8,1.8,1.8]),
          'icosphere':lambda:trimesh.creation.icosphere(subdivisions=3,radius=1),
          'cone':lambda:trimesh.creation.cone(radius=1,height=2,sections=64),
          'cylinder':lambda:trimesh.creation.cylinder(radius=.8,height=2,sections=64),
          'capsule':lambda:trimesh.creation.capsule(height=1.5,radius=.6),
          'torus':lambda:trimesh.creation.annulus(r_min=.55,r_max=1.1,height=.35,sections=64),
        }
        mesh=shapes[form]()
        rgb=bytes.fromhex(color[1:]);mesh.visual.vertex_colors=[(*rgb,255)]*len(mesh.vertices)
        path=folder/('NOX_3D_'+form+'.glb')
        path.write_bytes(trimesh.Scene(mesh).export(file_type='glb'))
        return {'status':'PROCEDURAL_3D_READY','project_id':pid,
                'path':path.name,'bytes':path.stat().st_size,'format':'GLB',
                'note':'Real GLB file; generated from a procedural geometric primitive, not AI text-to-3D'}

    def speak(self,text,project_id='',language='ru'):
        """Real local TTS via an installed system binary; not a simulated voice."""
        from .engine import StudioError
        if not isinstance(text,str) or not 1<=len(text)<=1500:
            raise StudioError('Voice text must be 1..1500 characters')
        if language not in ('ru','es','en'):raise StudioError('Unsupported voice language')
        tts=shutil.which('espeak-ng') or shutil.which('espeak')
        if not tts:raise StudioError('Local eSpeak TTS not installed. Configure an approved voice engine.')
        pid=project_id or uuid.uuid4().hex[:12];folder=self._project(pid)
        path=folder/'NOX_VOICE.wav'
        res=subprocess.run([tts,'-v',language,'-w',str(path),'--',text],
                           capture_output=True,timeout=60,check=False)
        if res.returncode or not path.is_file() or not path.stat().st_size:
            raise StudioError('TTS engine failed: '+res.stderr.decode('utf-8','replace')[-300:])
        return {'status':'VOICE_READY','project_id':pid,'path':path.name,
                'engine':Path(tts).name,'bytes':path.stat().st_size,'language':language,
                'note':'System TTS voice, not photorealistic cloned speech'}

    def chat_execute(self,text,project_id='',scenes=6):
        """Execute *explicit* natural-language creation requests from normal NOX chat."""
        from .engine import StudioError
        route=self.chat_route(text)
        if not route.get('handled'):return {'handled':False}
        stripped=text.lower().strip()
        if not any(stripped.startswith(v) for v in CREATION_VERBS):
            return {**route,'status':'READY_TO_CONFIRM',
                    'next':'Say Создай/Сделай for execution, or open the Studio buttons'}
        kind=route['kind']
        if kind in ('movie','cartoon2d','cartoon3d','anime','adult18','video'):
            return {'handled':True,'kind':kind,**self.storyboard(text,kind,scenes,project_id)}
        if kind in ('site','slides','code','voice','sound','memory','learning'):
            return {'handled':True,'kind':kind,**self.create_text(kind,text,project_id)}
        if kind=='3d':
            shape='cube' if ('куб' in stripped or 'cube' in stripped) else 'cone' if 'конус' in stripped else 'sphere'
            return {'handled':True,'kind':kind,**self.make_3d(project_id,shape)}
        if kind=='photo':
            workflows=sorted(self.workflows.glob('*.json'))
            if len(workflows)!=1:return {'handled':True,'kind':kind,'status':'NEEDS_WORKFLOW',
                            'next':'Select installed ComfyUI image workflow and text node'}
            return {'handled':True,'kind':kind,**self.workflow(workflows[0].name,'6',text)}
        raise StudioError('No installed provider for this request')
