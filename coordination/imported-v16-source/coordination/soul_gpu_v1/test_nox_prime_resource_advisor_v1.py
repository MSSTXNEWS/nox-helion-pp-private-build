"""NOX resource-advice deterministic contract tests (no GPU/network)."""
from unittest import TestCase, main
from unittest.mock import patch
import nox_prime_resource_advisor_v1 as a

class ResourceAwarenessTests(TestCase):
    def sample(self):
        return {'observed_at_utc':'2026-11-07T13:00:00+00:00',
                'training_active':True,
                'gpu':{'name':'AMD Radeon RX 6650M','source':'LHM',
                       'total_gib':8.0,'used_gib':5.75}}

    def test_busy_training_note(self):
        x=a.advise('video',self.sample())
        self.assertIn('занята обучением',x['message'])
        self.assertEqual(x['free_vram_gib'],2.25)
        self.assertIsNone(x['required_vram_gib'])
        self.assertFalse(x['subjective_consciousness_verified'])

    def test_never_invent_vram(self):
        x=a.advise('image',self.sample(),{'required_vram_gib':20.0})
        self.assertIsNone(x['required_vram_gib'])
        self.assertIn('наугад',x['message'])

    def test_verified_requirement(self):
        p={'model':'ImageModel','evidence':'verified-probe-123','required_vram_gib':6.0}
        x=a.advise('image',self.sample(),p)
        self.assertEqual(x['shortage_gib'],3.75)
        self.assertIn('verified-probe-123',x['message'])

    def test_missing_measurements_unknown_not_zero(self):
        x=a.advise('train',{'gpu':{'total_gib':8.0,'used_gib':None},
                              'training_active':None})
        self.assertIsNone(x['free_vram_gib'])
        self.assertIn('неизвестна',x['message'])

    def test_user_intent(self):
        self.assertEqual(a.task_from_text('Хочу селфи'), 'image')
        self.assertEqual(a.task_from_text('Сделай видео'), 'video')
        self.assertEqual(a.task_from_text('Создай приложение'), 'code')
        self.assertEqual(a.task_from_text('Продолжи LoRA'), 'train')
        self.assertTrue(a.is_resource_question('Что с видеокартой?'))
        self.assertFalse(a.is_resource_question('Привет'))

    def test_lhm_absent_fail_unknown(self):
        with patch.object(a,'_json',side_effect=OSError):
            x=a.gpu_snapshot()
        self.assertIsNone(x['used_gib'])
        self.assertIsNone(x['hotspot_c'])

    def test_lhm_nested_gpu_not_other(self):
        tree={'Text':'PC','Children':[
            {'Text':'AMD Radeon RX 6650M','Children':[
                {'Text':'GPU Memory Total','Value':'8192 MiB'},
                {'Text':'GPU Memory Used','Value':'4096 MiB'},
                {'Text':'GPU Hot Spot','Value':'64.5 °C'}]},
            {'Text':'AMD Radeon 680M','Children':[
                {'Text':'GPU Memory Used','Value':'100 GB'}]}]}
        with patch.object(a,'_json',return_value=tree):
            x=a.gpu_snapshot()
        self.assertEqual(x['total_gib'],8.0)
        self.assertEqual(x['used_gib'],4.0)
        self.assertEqual(x['hotspot_c'],64.5)

if __name__=='__main__':
    main()
