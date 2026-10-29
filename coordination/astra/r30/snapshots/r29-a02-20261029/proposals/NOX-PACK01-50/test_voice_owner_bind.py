"""Original P02 owner voice/SIP contract tests: no live microphone, model or phone call."""
import importlib.util
import json
import os
import pathlib
import sys
import time
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nox_pack_owner",ROOT/"native_bridge.py")
bridge=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=bridge
spec.loader.exec_module(bridge)

owner=os.getenv("NOX_P02_OWNER_PATH")
if not owner:raise RuntimeError("PINNED_P02_OWNER_REQUIRED")
sys.path.insert(0,owner)
from p02_capabilities import Identity, LocalVoicePipeline, ConsentGatedSip
catalog=json.loads((ROOT/"catalog.json").read_text("utf-8"))

class VoiceOwnerTests(unittest.TestCase):
    def setUp(self):
        self.speech=[]
        self.calls=[]
        self.scope=Identity("tenant1","user1","HELION","approved-persona","sess1")
        self.voice=LocalVoicePipeline(
            lambda scope,data,language,stop:"привет",
            lambda scope,text,source,target,directive,stop:"Hola",
            lambda scope,text,lang,voice,stop:b"actual-synth-audio",
            approved_models=True,permitted_voices=frozenset({"es-voice"}))
        def provider(scope,quote,stop):
            self.calls.append(quote.quote_id)
            return {"simulatedProviderTest":True}
        self.sip=ConsentGatedSip(provider,user_approval=lambda scope,quote:True,
            provider_quote_verify=lambda scope,quote:quote.currency=="EUR")
        self.quote=ConsentGatedSip.new_quote("+34950123456","Appointment","0.03",
            "EUR","provider-quote-001",time.time()+60)
        self.authorized=[False]
        self.host=bridge.NoxPackHost(catalog,
            native_approve=lambda session,route,args:self.authorized[0])
        self.adapter=bridge.ExistingP02VoiceAdapter(self.voice,self.sip,
            native_identity=lambda session:self.scope,
            native_microphone_sample=lambda session:b"local-audio-only",
            native_provider_quote=lambda session:self.quote)
        self.bound=self.adapter.register(self.host,receipt="PINNED-P02-VOICE-CONTRACT")
        self.session=bridge.NativeSession("tenant1","user1","room1",allowed=self.bound,
            private_approved=self.bound)

    def test_original_voice_owner_four_routes_wired(self):
        self.assertEqual(self.bound,
            frozenset({"translate.ru_es","maestro.spanish","calls.dial","voice.settings"}))
        self.assertTrue(self.host.advertise(self.session)["translate.ru_es"]["enabled"])
        self.assertFalse(self.host.advertise(self.session)["calls.dial"]["enabled"])

    def test_voice_settings_are_installed_owner_identities_only(self):
        item=self.host.execute("voice.settings",{},self.session)
        self.assertEqual(item["voices"],["es-voice"])
        self.assertEqual(item["voiceCount"],1)
        self.assertTrue(item["modelsApproved"])

    def test_translation_real_owner_pipeline_on_local_fixture(self):
        out=self.host.execute("translate.ru_es",
            {"direction":"ru-es","voiceId":"es-voice"},self.session)
        self.assertEqual(out["answer"],"Hola")
        self.assertEqual(out["source"],"ru")
        self.assertEqual(out["audio"],b"actual-synth-audio")

    def test_teacher_uses_same_owner_pipeline_without_new_llm(self):
        out=self.host.execute("maestro.spanish",
            {"direction":"ru-es","voiceId":"es-voice","level":"A1"},self.session)
        self.assertEqual(out["mode"],"maestro")

    def test_voice_missing_weights_is_hold(self):
        self.voice.approved_models=False
        with self.assertRaises(bridge.HostHold):
            self.host.execute("translate.ru_es",
                {"direction":"ru-es","voiceId":"es-voice"},self.session)

    def test_voice_unknown_id_rejected(self):
        with self.assertRaises(bridge.HostDenied):
            self.host.execute("translate.ru_es",
                {"direction":"ru-es","voiceId":"not-installed"},self.session)

    def test_call_requires_fresh_native_confirm_not_client_field(self):
        with self.assertRaises(bridge.HostDenied):
            self.host.execute("calls.dial",{"userConfirmed":True},self.session)
        self.assertEqual(self.calls,[])

    def test_owner_quote_accepted_once_and_replay_rejected(self):
        self.authorized[0]=True
        out=self.host.execute("calls.dial",{},self.session)
        self.assertTrue(out["simulatedProviderTest"])
        with self.assertRaises(PermissionError):
            self.host.execute("calls.dial",{},self.session)
        self.assertEqual(self.calls,["provider-quote-001"])

if __name__=="__main__":unittest.main()
