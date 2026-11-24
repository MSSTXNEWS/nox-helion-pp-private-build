import React, { useEffect, useRef } from 'react';
import 'deep-chat';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function viaChat(text) {
  const inp = document.querySelector('#input'), form = document.querySelector('#form'); if (!inp || !form) return 'Чат недоступен';
  const before = document.querySelectorAll('#msgs .m.a').length;
  inp.value = text; inp.dispatchEvent(new Event('input', { bubbles: true })); form.requestSubmit();
  for (let i = 0; i < 60 && !document.body.classList.contains('nox-busy') && document.querySelectorAll('#msgs .m.a').length === before; i++) await wait(100);
  for (let i = 0; i < 1500 && document.body.classList.contains('nox-busy'); i++) await wait(200);
  await wait(300); const a = [...document.querySelectorAll('#msgs .m.a .txt')].pop(); return a ? a.innerText.trim() || '(пустой ответ)' : '(нет ответа)';
}
export default function VoicePanel({ onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const d = ref.current; if (!d) return;
    d.connect = { stream: false, handler: async (body, signals) => { try { const m = body.messages[body.messages.length - 1]; const text = await viaChat(m.text || ''); signals.onResponse({ text }); } catch (e) { signals.onResponse({ error: String(e.message || e) }); } } };
    d.speechToText = { webSpeech: { language: 'ru-RU' }, submitAfterSilence: 2.5, displayInterimResults: true, button: { default: { container: { default: { width: '3.2rem', height: '3.2rem', borderRadius: '50%' } } } } };
    d.textToSpeech = { enabled: true, lang: 'ru-RU', rate: 1, pitch: 1, volume: 1 };
    d.introMessage = { text: 'Нажмите микрофон и говорите: ответ NOX придёт текстом и голосом. Если браузер не поддерживает распознавание речи, пишите в строке ниже.' };
    d.textInput = { placeholder: { text: 'Скажите или напишите…', style: { color: '#9a8f88' } }, styles: { container: { backgroundColor: 'rgba(20,14,12,.7)', border: '1px solid rgba(255,130,80,.25)', borderRadius: '14px', color: '#f1e6df' } } };
    d.messageStyles = { default: { user: { bubble: { backgroundColor: 'rgba(255,110,60,.18)', color: '#f6e9e2' } }, ai: { bubble: { backgroundColor: 'rgba(30,22,20,.8)', color: '#f1e6df' } } } };
    d.chatStyle = { backgroundColor: 'transparent', border: 'none', width: '100%', height: '100%', fontFamily: 'inherit' };
  }, []);
  return <aside className="nui-voice" aria-label="Голосовой режим"><header><b>Голосовой режим</b><span className="nui-hint">Deep Chat · Web Speech</span><button type="button" aria-label="Закрыть" onClick={onClose}>×</button></header><div className="nui-voice-body"><deep-chat ref={ref} style={{ width: '100%', height: '100%' }} /></div></aside>;
}
