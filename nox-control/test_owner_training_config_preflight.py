import ast
from dataclasses import dataclass,field
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('owner_training_config_preflight',HERE/'owner_training_config_preflight.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)


@dataclass
class StrictConfig:
    # Deliberately strict constructor: no **kwargs and no removed save_safetensors.
    output_dir:str='old'
    per_device_train_batch_size:int=1
    gradient_accumulation_steps:int=16
    max_length:int=2048
    max_steps:int=1000
    fp16:bool=True
    bf16:bool=False
    packing:bool=False
    gradient_checkpointing:bool=True
    gradient_checkpointing_kwargs:dict=field(default_factory=dict)
    dataloader_num_workers:int=0
    logging_steps:int=5
    save_steps:int=50
    save_total_limit:int|None=6
    warmup_steps:int=120
    learning_rate:float=0.0001
    optim:str='paged_adamw_8bit'
    lr_scheduler_type:str='cosine'
    report_to:list=field(default_factory=list)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.native=b'def build_trainer(model,tok,ds,smoke:bool,max_steps:int):\n return None\n'
        self.hybrid=b'def build_existing_trainer(native,model,tokenizer,dataset,planned:int,torch):\n return None\n'
        self.patcher=patch.object(g,'NATIVE_SHA',hashlib.sha256(self.native).hexdigest());self.patcher.start();self.addCleanup(self.patcher.stop)
        self.good={'schema':g.SCHEMA,'state':'INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED',
          'configuration':g.EXPECTED.copy(),'output_dir_match':True,'constructor_branch':'sftconfig',
          'config_class_module':'trl.trainer.sft_config','config_class_name':'SFTConfig',
          'config_alias_restored':True,'serialized_bytes':4021,'model_loaded':False,'dataset_loaded':False,
          'optimizer_created':False,'real_trainer_created':False,'cuda_visible_devices':'1',
          'package_versions':{'torch':'2.6.0+cu124','transformers':'5.23.0','trl':'1.18.0','accelerate':'1.15.0','peft':'0.21.3'}}

    def response(self,value=None,code=0):
        return types.SimpleNamespace(returncode=code,stdout=json.dumps(self.good if value is None else value).encode())

    def test_only_two_function_asts_no_top_level_source_is_executed(self):
        raw=b'raise RuntimeError("module execution forbidden")\n'+self.hybrid
        extracted=g.function_source(raw,'build_existing_trainer')
        self.assertEqual(len(ast.parse(extracted).body),1)
        self.assertNotIn('module execution forbidden',extracted)
        with self.assertRaisesRegex(RuntimeError,'FUNCTION'):
            g.function_source(self.hybrid+self.hybrid,'build_existing_trainer')

    def test_native_source_pin_checked_before_child(self):
        with patch.object(g.subprocess,'run') as child:
            with self.assertRaisesRegex(RuntimeError,'NATIVE_PIN'):g.run_preflight(self.hybrid,self.native+b'\n')
        child.assert_not_called()

    def test_success_preserves_real_fp16_and_1000_no_credentials_in_child(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'never-export','HF_TOKEN':'never-export','PYTHONPATH':'untrusted'}), \
             patch.object(g.subprocess,'run',return_value=self.response()) as child:
            result=g.run_preflight(self.hybrid,self.native)
        argv=child.call_args.args[0];kw=child.call_args.kwargs
        self.assertEqual(argv[:3],['/root/venv_volta/bin/python','-I','-c'])
        self.assertEqual(kw['timeout'],50);self.assertEqual(kw['stderr'],subprocess.DEVNULL)
        self.assertEqual(kw['env']['CUDA_VISIBLE_DEVICES'],'1')
        self.assertNotIn('OPENAI_API_KEY',kw['env']);self.assertNotIn('HF_TOKEN',kw['env']);self.assertNotIn('PYTHONPATH',kw['env'])
        payload=json.loads(kw['input']);self.assertIs(payload['expected']['fp16'],True)
        self.assertEqual(payload['expected']['max_steps'],1000)
        self.assertEqual(result['hybrid_sha256'],hashlib.sha256(self.hybrid).hexdigest())

    def test_timeout_and_raw_failure_never_export_exception_text(self):
        with patch.object(g.subprocess,'run',side_effect=subprocess.TimeoutExpired('secret args',50)):
            with self.assertRaisesRegex(RuntimeError,'^HOLD_CONFIG_PREFLIGHT_TIMEOUT$'):g.run_preflight(self.hybrid,self.native)
        with patch.object(g.subprocess,'run',return_value=self.response({'reason':'https://secret.invalid/?token=private'},2)):
            with self.assertRaisesRegex(RuntimeError,'^HOLD_CONFIG_PREFLIGHT_CHILD_FAILED$'):g.run_preflight(self.hybrid,self.native)

    def test_local_class_legacy_branch_or_execution_rejected(self):
        for key,value in (('config_class_module','__main__'),('config_class_name','BoundedConfig'),
                          ('constructor_branch','legacy'),('optimizer_created',True),('model_loaded',True),
                          ('real_trainer_created',True),('config_alias_restored',False),('serialized_bytes',0)):
            candidate={**self.good,key:value}
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'RESULT_REJECTED'):
                g.validate_result(candidate)

    def test_extra_private_result_fields_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'RESULT_SCHEMA'):
            g.validate_result({**self.good,'exception':'private'})

    def test_configuration_change_is_not_silently_allowed(self):
        candidate={**self.good,'configuration':{**g.EXPECTED,'fp16':False}}
        with self.assertRaisesRegex(RuntimeError,'RESULT_REJECTED'):g.validate_result(candidate)

    def test_child_compiles_and_uses_real_serializer_without_model_loading(self):
        compile(g.CHILD,'<preflight-child>','exec')
        self.assertIn('torch.save(args,memory)',g.CHILD)
        self.assertIn('type(args) is not RealConfig',g.CHILD)
        self.assertNotIn('from_pretrained',g.CHILD)
        self.assertNotIn('torch.load',g.CHILD)

    def test_corrected_factory_returns_pickleable_original_class_and_restores_alias(self):
        trl=types.ModuleType('trl');sub=types.ModuleType('trl.trainer')
        sft=types.ModuleType('trl.trainer.sft_trainer')
        trl.trainer=sub;sub.sft_trainer=sft;trl.SFTConfig=sft.SFTConfig=StrictConfig
        trl.SFTTrainer=object
        modules={'trl':trl,'trl.trainer':sub,'trl.trainer.sft_trainer':sft}
        namespace={'Path':Path,'OUTPUT':Path('/synthetic/unused'),'types':types,
                   'fp32_adapters':lambda *a,**kw:None,'optimizer_fp32':lambda *a,**kw:None}
        source=g.function_source((HERE/'hybrid_training_entry.py').read_bytes(),'build_existing_trainer')
        exec(compile(source,'<actual-hybrid-function>','exec'),namespace)
        def native_builder(model,tokenizer,dataset,smoke,planned):
            from trl import SFTConfig
            args=SFTConfig(output_dir='old',max_steps=planned,save_safetensors=True)
            return types.SimpleNamespace(model=model,args=args,optimizer=None,
                        create_optimizer=lambda:None,compute_loss=lambda *a,**kw:None)
        with patch.dict(sys.modules,modules):
            trainer=namespace['build_existing_trainer'](types.SimpleNamespace(build_trainer=native_builder),
                       object(),object(),object(),1000,object())
            self.assertIs(type(trainer.args),StrictConfig)
            self.assertIs(trl.SFTConfig,StrictConfig)
            # Native legacy True is removed only if the real config lacks it.
            # False must fail closed; no silent unsafe checkpoint format.
            def unsafe_native(model,tokenizer,dataset,smoke,planned):
                from trl import SFTConfig
                return SFTConfig(output_dir='old',max_steps=planned,save_safetensors=False)
            with self.assertRaisesRegex(RuntimeError,'HOLD_NATIVE_UNSAFE_SAVE_FORMAT'):
                namespace['build_existing_trainer'](
                    types.SimpleNamespace(build_trainer=unsafe_native),
                    object(),object(),object(),1000,object())
            self.assertIs(trl.SFTConfig,StrictConfig)
            def unknown_native(model,tokenizer,dataset,smoke,planned):
                from trl import SFTConfig
                return SFTConfig(output_dir='old',max_steps=planned,unknown_setting=True)
            with self.assertRaisesRegex(RuntimeError,'HOLD_NATIVE_SFTCONFIG_UNSUPPORTED_ARGUMENT'):
                namespace['build_existing_trainer'](
                    types.SimpleNamespace(build_trainer=unknown_native),
                    object(),object(),object(),1000,object())
            self.assertIs(trl.SFTConfig,StrictConfig)
            restored=pickle.loads(pickle.dumps(trainer.args))
            self.assertEqual(restored,trainer.args)
            self.assertEqual(restored.max_length,256);self.assertEqual(restored.gradient_accumulation_steps,1)
            self.assertIs(restored.fp16,True)
            def broken(*args):raise TypeError('synthetic constructor failure')
            with self.assertRaisesRegex(TypeError,'synthetic constructor failure'):
                namespace['build_existing_trainer'](types.SimpleNamespace(build_trainer=broken),
                            object(),object(),object(),1000,object())
            self.assertIs(trl.SFTConfig,StrictConfig)

    def test_removed_keyword_and_old_local_subclass_fail_at_the_real_seams(self):
        with self.assertRaisesRegex(TypeError,'save_safetensors'):
            StrictConfig(save_safetensors=True)
        class BoundedConfig(StrictConfig):pass
        with self.assertRaises((AttributeError,pickle.PicklingError)):
            pickle.dumps(BoundedConfig())


if __name__=='__main__':unittest.main()
