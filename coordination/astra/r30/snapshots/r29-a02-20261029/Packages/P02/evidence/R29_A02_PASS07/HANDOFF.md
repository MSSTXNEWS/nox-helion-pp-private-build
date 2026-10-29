# R29 A02 PASS07 — captured voice consent/request/result donor consolidation

Parent e7175b6058394a7a13b89a407266e83b37d27987; owner astra/r29-a02-20261029. SOURCE_COMPONENT_VERIFIED. A02 7/10 tested approaches, not product acceptance. Scope maps to R29 matrix A02 approach 08 and V16 §26.4 item 8. The matrix's task_ids list is empty; no canonical accepted TaskID or denominator is invented.

The current owner source lacked ready R27 A05 consent/request/result safety: native capture was consumed with microphone_consent=True without capture-specific native proof; callbacks could change the request; malformed/mismatched provider output could reach later adapters/native storage; model/provider rights could change between stages. These were confirmed by replaying the existing donor tests against e7175b6 source, then repaired by reusing the reviewed donor implementation.

## Exact reused source and preserved overlays

R27 A05 p02_capabilities.py donor Git blob d721cd9608d62052060ae2c7ff6db240b281802f: copied exact _voice_text helper and LocalVoicePipeline class only. It freezes permitted voices, snapshots provider callables, validates RU↔ES/voice/mode/CEFR before native consumption, requires exact True consent/model rights, checks revocation/provider changes after each stage, rejects malformed UTF-8/blank/oversized text and validates final result provenance/size. SIP classes remain byte-identical to e7175b6.

R27 A05 p02_owner_route_ports.py donor Git blob dcef668c010b9b215131e610eab960a3d864ec14: reused exact OwnerTwoPorts section. Native microphone permission/consent must be proven by the trusted callback for the exact capture ID; unavailable/denied/exception/STOP paths preserve unconsumed audio. Request primitives are snapshotted before callbacks. Provider output is checked before native storage. The already-reused STOP-after-persistence cleanup is retained. R29 registration helper remains byte-identical; original VoiceSession lifecycle/atomic retirement/queued-session ingress is unchanged.

Four original donor test files and the donor's explicit test-only consent fixture were reused exactly. No original 729 file, donor branch, PACK01 host, SourceLock/stager pin or other owner file changed. receipt.json supplies exact pre/post overlay blobs/SHA256. This is same-owner source consolidation, not final host integration.

## Test evidence

RED: 20 donor tests; 28 failed subcases and 11 errors against previous current source. Failures include absent native-proof gate, capture consumed before invalid request rejection, request mutation, invalid provider text/result accepted, truthy permissions accepted, provider/rights changes and externally mutable voice whitelist.

GREEN: 66 selected unique unittest methods: 20 donor tests plus all 46 prior ingress/host/STOP methods. Includes both RU→ES and ES→RU/MAESTRO, Unicode/emoji, native proof exactness and capture preservation, provider chain and cancellation boundaries, plus real original VoiceSession subprocess termination and atomic completion/STOP. No live microphone, installed model, Windows loader or outbound call was exercised.

```
NOX_ORIGINAL_SOURCE_ZIP=/path/to/verified-original-729.zip PYTHONPATH=Packages/P02/worker-python python -m unittest test_p02_native_ingress.IngressTests test_p02_owner_route_ports.RouteTests test_p02_loader_voice_stop_r29.VoiceStopWiring test_p02_loader_existing_pack_r29.ExistingPackContract test_p02_native_voice_lifecycle_r29.NativeVoiceLifecycle test_p02_voice_consent_r27.ConsentTests test_p02_voice_request_r27.RequestTests test_p02_voice_result_r27.ResultTests test_p02_voice_lifecycle_r27.LifecycleTests -v
```

Archive SHA256 remains ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a. Before this block all56 rules, C34 tail and OPTIMIZATION02_DELTA were read; root writes journals. elapsed.json records measured preparation interval after initial rules/donor inspection, not a fabricated full-session duration or projected time saving.

## Finite remaining obligations (known scope, not a global product denominator)

| Matrix/spec key | Exact path or contract | Remaining type and evidence |
| --- | --- | --- |
| A02 approach08 / V16 §26.4.8 | Packages/P02/worker-python/p02_owner_route_ports.py:OwnerTwoPorts; p02_native_ingress.py | FUTURE NATIVE COMPOSITION: native_mic_consent(scope,capture_id) must reflect real OS permission and current user approval; provide native_take_audio/store_output_audio/discard_output_audio; keep stable authenticated NativeSession; bind ingress.voice_stop_token and share original VoiceSession with real ASR/TTS. This pass implements gates, not fabricated approval/provider adapters. |
| A02 approach03 / V16 §26.4.3 | Packages/P02/worker-python/p02_runtime.py and p02_chat_bridge.py | READY SAME-OWNER DONOR RECONCILIATION: remaining R27 A04 strict stream/protocol/epoch and chat snapshot candidates need a scoped merge with the R29 timeout overlay. Not reopened STOP lifecycle work; not a claimed missing new backend. |
| A02 approach09 / V16 §26.4.9 | Packages/P02/worker-python/p02_capabilities.py: SIP call quote/place section | READY SAME-OWNER DONOR RECONCILIATION: R27 A05 quote expiry/finite time/STOP-after-provider-and-consent callbacks still reside on donor branch. Unchanged here to keep the block focused on captured voice. Real SIP provider/price/native approval afterward is a separate composition/acceptance obligation. |
| A02 approach08+10 / V16 §26.4.8,10 | Existing Windows host and real microphone/ASR/TTS/RU↔ES output | NATIVE VERIFICATION: real device permission, both directions/MAESTRO, audible output/quality and STOP during actual providers, same-SHA independent QA. No source-only mock can close it. |

Lesson applied: replay ready donor functional tests against current source, transplant only connected proven sections, and retain prior lifecycle overlays exactly. This closes identifiable source omissions without rewriting engines or counting donor tests as new product acceptance.
