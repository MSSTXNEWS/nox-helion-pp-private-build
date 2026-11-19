"""NOX V104 test: no fake consciousness or lower quality for complex queries."""
import unittest
from nox_runpod.teacher_mesh.v104.fast_quality_policy import (
    choose_model_options,cache_reuse_admission)
SHA="a"*64
def run(prompt,**opts):
    args=dict(owner_authenticated=True,model_sha256=SHA,s03_revision="s03-epoch1")
    args.update(opts)
    return choose_model_options(prompt,**args)

class FastMode(unittest.TestCase):
    def test_ru_one_word_is_safe_fast(self):
        q=run("Ответь одним словом: готово.")
        self.assertEqual(q["state"],"READY_FAST_SIMPLE_QUERY")
        self.assertEqual(q["chat_template_kwargs"]["enable_thinking"],False)
        self.assertFalse(q["native_onehost_bound"])
    def test_es_one_word_is_safe_fast(self):
        self.assertEqual(run("Responde solo con una palabra: listo.")["thinking"],False)
    def test_greetings_ru_es_en(self):
        for t in ("Привет","Здравствуйте","Hola","hello"):
            self.assertFalse(run(t)["thinking"])
    def test_full_depth_for_self_awareness(self):
        for t in ("Кто ты и как зародился NOX?",
                  "Вспомни все свои предыдущие ошибки и объясни причины.",
                  "Проверь и исправь код тренера.",
                  "Как мне сохранить память S03?"):
            self.assertTrue(run(t)["thinking"])
    def test_sensitive_and_unknown_prompts_deep(self):
        for t in ("Можешь дать совет по здоровью?",
                  "Какой срок рассмотрения по закону?",
                  "Проанализируй мои требования",
                  "Что лучше выбрать сегодня?"):
            self.assertTrue(run(t)["thinking"])
    def test_tools_request_even_simple_prompt_is_deep(self):
        self.assertTrue(run("привет",tool_use_required=True)["thinking"])
    def test_invalid_or_anonymous_denied(self):
        self.assertEqual(run("  ")["state"],"HOLD_INVALID_PROMPT")
        self.assertEqual(run("Привет",owner_authenticated=False)["state"],
                         "HOLD_OWNER_AUTH_OR_STOP")
    def test_stop_cannot_be_bypassed_by_cache(self):
        self.assertEqual(run("Привет",stop_active=True)["state"],
                         "HOLD_OWNER_AUTH_OR_STOP")
    def test_no_valid_model_sha_never_fast(self):
        self.assertEqual(run("Привет",model_sha256="bad")["state"],
                         "HOLD_MODEL_SOURCE_SHA")
    def test_s03_revision_required(self):
        self.assertEqual(run("Привет",s03_revision=None)["state"],
                         "HOLD_S03_REVISION")
    def test_fast_still_does_not_automatically_enable_kv_cache(self):
        q=run("привет")
        self.assertFalse(q["cache_prompt"])
        self.assertFalse(q["performed"])
    def test_kv_cache_requires_all_auth_model_memory_and_scope(self):
        x=dict(owner_scope_verified=True,same_owner_session=True,
               same_model_sha=True,same_s03_revision=True,
               native_slot_scope_verified=True,stop_active=False)
        self.assertTrue(cache_reuse_admission(**x)["eligible_for_native_owner_integration"])
        for field in ("owner_scope_verified","same_owner_session","same_model_sha",
                      "same_s03_revision","native_slot_scope_verified"):
            altered=x.copy();altered[field]=False
            self.assertFalse(cache_reuse_admission(**altered)["eligible_for_native_owner_integration"])
        altered=x.copy();altered["stop_active"]=True
        self.assertFalse(cache_reuse_admission(**altered)["eligible_for_native_owner_integration"])
    def test_policy_is_not_deployed_claim(self):
        self.assertFalse(run("Привет")["native_onehost_bound"])
        self.assertFalse(cache_reuse_admission(owner_scope_verified=False,
            same_owner_session=False,same_model_sha=False,same_s03_revision=False,
            native_slot_scope_verified=False,stop_active=False)["applied_to_live_llama"])
if __name__=="__main__":unittest.main()
