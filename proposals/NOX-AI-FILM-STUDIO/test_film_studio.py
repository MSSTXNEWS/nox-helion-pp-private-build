import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent/"NOX-SUPER-CINEMA-3D"))
from film_studio import (STYLES,Scene,Character,FilmProject,new_project,validate,
                         storyboard,style_prompt,submit_scene,receive_scene_output,save_project,load_project,
                         Denied,Hold)
from render import Clip,srt_time,subtitles,export_movie
from comfy_video_bridge import ComfyVideoPort, NativeVideoPreflight

H="a"*64
PID="abcde123-1234-5678-9012-abcdefabcdef"

def project(*, style="anime",rating="GENERAL", adult=False, chars=(), scenes=None):
    if scenes is None:
        scenes=(Scene("s-opening","Opening","cinematic aerial view",3, dialogue="Привет, мир"),)
    p=FilmProject("NOX_FILM_PROJECT_V1","studio-test","Тестовый фильм",style,
         rating,adult,True,tuple(chars),tuple(scenes))
    validate(p)
    return p

class FakeComfy:
    def __init__(self):
        self.requests=[]
    def request(self,method,route,payload=None):
        self.requests.append((method,route,payload))
        return {"prompt_id":PID}

class FilmTests(unittest.TestCase):
    def test_twelve_distinct_styles(self):
        self.assertEqual(len(STYLES),12)
        for s in STYLES:
            p=project(style=s,rating="ADULT_18" if s=="adult_anime_18" else "GENERAL",
                      adult=s=="adult_anime_18",
                      chars=(Character("adult-actor","Adult","verified adult",26,H,True,True),) if s=="adult_anime_18" else ())
            self.assertEqual(len(storyboard(p)),1)

    def test_adult_animation_requires_verified_adult_character(self):
        with self.assertRaises(Denied):
            project(style="adult_anime_18")
        minor=Character("actor-one","Actor","adult-looking",17,H,True,True)
        with self.assertRaises(Denied):
            project(style="adult_anime_18",rating="ADULT_18",adult=True,chars=(minor,))
        no_attestation=replace(minor,age=28,adult_appearance_attested=False)
        with self.assertRaises(Denied):
            project(style="adult_anime_18",rating="ADULT_18",adult=True,chars=(no_attestation,))
        ok=replace(no_attestation,adult_appearance_attested=True)
        self.assertEqual(project(style="adult_anime_18",rating="ADULT_18",adult=True,chars=(ok,)).style,
                         "adult_anime_18")

    def test_rights_and_profiles_must_be_approved(self):
        with self.assertRaises(Denied):
            new_project("studio-test","title")
        p=project()
        with self.assertRaises(Denied):
            validate(replace(p,source_rights_approved=False))
        with self.assertRaises(Hold):
            validate(replace(p,fps=120))
        with self.assertRaises(Hold):
            validate(replace(p,width=4096))

    def test_storyboard_chapter_timeline_and_character_consistency(self):
        c=Character("hero-one","Герой","black coat",26,H,True,True)
        s=(Scene("s-001","City","cinematic city",5,character_ids=("hero-one",)),
           Scene("s-002","Sun","sunset scene",8,character_ids=("hero-one",)))
        p=project(chars=(c,),scenes=s)
        board=storyboard(p)
        self.assertEqual([(x["startSecond"],x["endSecond"]) for x in board],[(0,5),(5,13)])
        self.assertIn("Герой",board[0]["prompt"])

    def test_invalid_scene_or_unverified_output_rejected(self):
        p=project()
        with self.assertRaises(Hold):
            validate(replace(p,scenes=(replace(p.scenes[0],status="RENDERED"),)))
        with self.assertRaises(Hold):
            validate(replace(p,scenes=(replace(p.scenes[0],seconds=21),)))
        with self.assertRaises(Hold):
            validate(replace(p,scenes=(replace(p.scenes[0],reference_sha256=None,operation="i2v"),)))
        with self.assertRaises(Hold):
            validate(replace(p,scenes=(replace(p.scenes[0],character_ids=("unknown",)),)))
        with self.assertRaises(Hold):
            validate(replace(p,scenes=(replace(p.scenes[0],provider_id="fictional-provider"),)))

    def test_real_comfy_queue_and_truthful_queued_status(self):
        p=project()
        workflow={"6":{"class_type":"CLIPTextEncode","inputs":{"text":"old"}}}
        digest=hashlib.sha256(json.dumps(workflow,sort_keys=True,separators=(",",":"),ensure_ascii=False)
            .encode()).hexdigest()
        preflight=NativeVideoPreflight("wan21-t2v-1.3b",digest,H,True,True,True,
                                     True,12,9,False)
        fake=FakeComfy()
        adapter=ComfyVideoPort(fake)
        result=submit_scene(p,"s-opening",port=adapter,workflow=workflow,workflow_sha256=digest,
                            prompt_node="6",preflight=preflight,client_id="NOX-FILM-TEST",
                            user_authorized=True)
        self.assertEqual(result["status"],"QUEUED_NOT_RENDERED")
        self.assertFalse(result["rendered"])
        self.assertEqual(len(fake.requests),1)
        self.assertEqual(fake.requests[0][0:2],("POST","/prompt"))
        with self.assertRaises(Denied):
            submit_scene(p,"s-opening",port=adapter,workflow=workflow,workflow_sha256=digest,
                prompt_node="6",preflight=preflight,client_id="NOX-FILM-TEST",user_authorized=False)

    def test_native_verified_output_receipt_only(self):
        s=project().scenes[0]
        with self.assertRaises(Denied):
            receive_scene_output(s,output_sha256=H,output_filename="scene.mp4",
                                 native_host_verified=False)
        with self.assertRaises(Hold):
            receive_scene_output(s,output_sha256=H,output_filename="../bad.mp4",
                                 native_host_verified=True)
        s2=receive_scene_output(s,output_sha256=H,output_filename="scene.mp4",
                                native_host_verified=True)
        self.assertEqual(s2.status,"RENDERED")
        with self.assertRaises(Hold):
            validate(replace(project(),scenes=(replace(s2,output_sha256=None),)))

    def test_persistence_atomic_with_same_episode_and_no_network(self):
        p=project()
        with tempfile.TemporaryDirectory() as tmp:
            saved=save_project(p,Path(tmp))
            self.assertEqual(saved.name,"studio-test.json")
            recovered=load_project("studio-test",Path(tmp))
            self.assertEqual(recovered.scenes[0].dialogue,"Привет, мир")
            self.assertEqual(recovered.style,"anime")

    def test_subtitles_accurate_timecodes(self):
        p=project(scenes=(Scene("s-first","First","one",3,dialogue="Начало"),
                           Scene("s-next","Next","two",7,dialogue="Финал")))
        s=subtitles(p)
        self.assertIn("00:00:00,000 --> 00:00:03,000",s)
        self.assertIn("00:00:03,000 --> 00:00:10,000",s)

    def test_export_requires_complete_shots_real_bytes_and_native_approval(self):
        p=project()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            f=root/"shot.mp4"
            f.write_bytes(b"very-small-test-media" * 30)
            digest=hashlib.sha256(f.read_bytes()).hexdigest()
            verified=receive_scene_output(p.scenes[0],output_sha256=digest,
                                          output_filename="shot.mp4",native_host_verified=True)
            p=replace(p,scenes=(verified,))
            out=root/"output"
            calls=[]
            def fake_run(args,*,cwd,timeout,check,stdin,stdout,stderr):
                calls.append(args)
                Path(args[-1]).write_bytes(b"offline-ci-ffmpeg-output" * 20)
                class Result:returncode=0
                return Result()
            with self.assertRaises(Denied):
                export_movie(p,clip_root=root,clips=[Clip(verified.id,"shot.mp4",digest)],
                             output_root=out,ffmpeg_binary="ffmpeg.exe",user_approved=False,
                             ffmpeg_host_attested=True,runner=fake_run)
            result=export_movie(p,clip_root=root,clips=[Clip(verified.id,"shot.mp4",digest)],
                                output_root=out,ffmpeg_binary="ffmpeg.exe",user_approved=True,
                                ffmpeg_host_attested=True,runner=fake_run)
            self.assertEqual(result["status"],"FILE_EXPORTED_NOT_NATIVE_QA_ACCEPTED")
            self.assertTrue((out/"studio-test.mp4").exists())
            self.assertEqual(len(calls),2)
            self.assertTrue(any("-safe" in argv and "1" in argv for argv in calls))
            self.assertTrue((out/"studio-test.srt").exists())
            with self.assertRaises(Hold):
                export_movie(p,clip_root=root,clips=[Clip(verified.id,"shot.mp4",digest)],
                            output_root=out,ffmpeg_binary="ffmpeg.exe",user_approved=True,
                            ffmpeg_host_attested=True,runner=fake_run)

if __name__=="__main__":
    unittest.main()
