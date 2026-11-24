import React, { useMemo, useEffect } from 'react';
import { ReactFlow, Background, Controls, useReactFlow, ReactFlowProvider } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
const cut = (s, n) => { s = String(s).replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
function Inner({ store, emit, useStore, splitThinkRaw, urlsOf }) {
  useStore(); const t = store.turns[store.turns.length - 1]; const rf = useReactFlow();
  const { nodes, edges } = useMemo(() => {
    const N = [], E = []; if (!t) return { nodes: [{ id: 'e', position: { x: 0, y: 0 }, data: { label: 'В этой сессии ходов ещё нет: отправьте сообщение, и карта построится из реального потока ответа.' }, className: 'nf nf-q' }], edges: [] };
    const { think, ans } = splitThinkRaw(t.raw); let x = 0; const add = (id, label, cls, y = 0) => { N.push({ id, position: { x, y }, data: { label }, className: 'nf ' + cls }); x += 230; return id; };
    let prev = add('q', 'Запрос: ' + cut(t.msg, 70), 'nf-q'); const link = (a, b) => E.push({ id: a + '-' + b, source: a, target: b, animated: !t.done });
    t.levels.filter((v, i, a) => a.indexOf(v) === i).forEach((l, i) => { const id = add('l' + i, 'Уровень: ' + l, 'nf-l'); link(prev, id); prev = id; });
    const steps = think.split(/\n{2,}|(?<=[.!?])\s+(?=[А-ЯA-Z])/).map((s) => s.trim()).filter((s) => s.length > 12).slice(-6);
    steps.forEach((s, i) => { const id = add('s' + i, cut(s, 90), 'nf-s', (i % 2) * 70); link(prev, id); prev = id; });
    const a = add('a', (t.done ? 'Ответ' : 'Ответ пишется…') + ' · ' + ans.length + ' симв. · ' + t.chunks + ' чанков' + (t.done ? ' · ' + ((t.t1 - t.t0) / 1000).toFixed(1) + ' с' : ''), 'nf-a'); link(prev, a);
    urlsOf(ans).slice(0, 4).forEach((u, i) => { let h = u; try { h = new URL(u).hostname; } catch (e) { /* */ } N.push({ id: 'u' + i, position: { x: x - 230, y: 90 + i * 60 }, data: { label: h }, className: 'nf nf-u' }); E.push({ id: 'a-u' + i, source: 'a', target: 'u' + i }); });
    return { nodes: N, edges: E };
  }, [store.rev]);
  useEffect(() => { const id = setTimeout(() => rf.fitView({ padding: 0.15, duration: 300 }), 60); return () => clearTimeout(id); }, [nodes.length]);
  return <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: false }} nodesDraggable={false} colorMode="dark" minZoom={0.2}><Background gap={22} color="rgba(255,140,80,.12)" /><Controls showInteractive={false} /></ReactFlow>;
}
export default function FlowPanel(p) {
  return <aside className="nui-flow" aria-label="Карта мышления"><header><b>Карта мышления</b><span className="nui-hint">живой поток последнего хода</span><button type="button" aria-label="Закрыть" onClick={() => { p.store.flow = false; p.emit(); }}>×</button></header><div className="nui-flow-body"><ReactFlowProvider><Inner {...p} /></ReactFlowProvider></div></aside>;
}
