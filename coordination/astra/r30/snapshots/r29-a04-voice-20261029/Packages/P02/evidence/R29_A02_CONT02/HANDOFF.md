# R29 A02 continuation02 — original voice typed failure contract

Parent818bb8eca459ce5c0ca8745ac9cb7126527451b2. Previous queue10/10 retained; continuation2/10 tested blocks. Mapping V15 rule31 and R29 A02 approach08/10; product TaskID denominator N/D.

Concrete defect: original VoiceCancelled, VoiceTimeout and VoicePermissionDenied derive RuntimeError, so the existing native ingress converted all into NATIVE_PROVIDER_HOLD. The loader could not distinguish user STOP, provider timeout and denied permission despite those original types already carrying that distinction.

OriginalVoicePort now translates these exact original exception classes to fixed ProtocolHold codes: NATIVE_VOICE_STOPPED, NATIVE_VOICE_TIMEOUT, NATIVE_PERMISSION_DENIED. A late VoiceTimeout consults the SAME current original VoiceSession; confirmed native STOP wins. Arbitrary error text is never forwarded. Other provider failures retain the existing generic HOLD policy. No engine, host, byte-audio contract, timeout policy or permission grant was changed.

RED:3 tests with6 failing subcases, all observing NATIVE_PROVIDER_HOLD where a specific original type was known. GREEN:6 focused tests: timeout at original ASR/translation/SAPI boundaries, permission vs cancel, actual authorized STOP followed by late timeout, normal original preview/playback and review cancellation. Tests pass errors through actual NativeIngress and existing _encode_status into the native HOLD JSON schema; original class definitions are imported from the same verified729 archive. They verify no PRIVATE provider detail leaks and the active VoiceSession is retired after errors. Original worker/OS boundaries remain fixtures, not live physical inference/audio.

Command:
NOX_ORIGINAL_SOURCE_ZIP=/path/to/verified-original-729.zip PYTHONPATH=Packages/P02/worker-python python -m unittest test_p02_original_voice_outcomes_r29.OriginalVoiceOutcomes test_p02_original_voice_port_r29.OriginalVoiceContract.test_original_preview_never_autoplays_or_invents_audio_storage test_p02_original_voice_port_r29.OriginalVoiceContract.test_original_sapi_dict_is_native_receipt_after_bound_native_review test_p02_original_voice_port_r29.OriginalVoiceContract.test_stop_in_native_review_cancels_original_session_before_sapi -v

Remaining known scoped obligations are unchanged from CONT01: real authenticated host one-use capture bindings and current OS/mic permission; physical native preview UI/model rights; host composition including independent E06cbfe853 mutation fix; Windows same-SHA physical verification. Those native callbacks are not supplied by original PushToTalk's raw-WAV return interface and cannot be fabricated by this P02 adapter. Original sources remain unchanged and no final host integration/build/CI ran. No additional independently confirmed owned code defect is claimed merely to fill the continuation queue.

Lesson: adapt existing typed error ownership at the provider boundary; never replace a confirmed STOP with a later timeout or expose untrusted provider exception strings in privileged protocol frames.
