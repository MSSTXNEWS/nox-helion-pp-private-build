"""Dark glass persona HUD for M2.3. Chips copy TurnGate state; they do not invent it."""
from __future__ import annotations

import tkinter as tk

from helion.personas import PERSONAS, get_persona

BG = '#070B10'
GLASS = '#101820'
LINE = '#2A4458'
AMBER = '#E8B15A'
CYAN = '#3EE0D2'
TEXT = '#E7F2F4'
MUTED = '#8AA0A8'
INK = '#071016'
HALT = '#FF5A3C'
OK = '#8FDBB2'

ACCENT = {
    'persona.kairen_voss': '#E8B15A',
    'persona.adrian_marrow': '#3EE0D2',
    'persona.leon_ardis': '#7EB6FF',
    'persona.elina_veil': '#F2A3C7',
    'persona.kassien_veir': '#F07A3A',
}
CODE = {
    'persona.kairen_voss': 'KV',
    'persona.adrian_marrow': 'AM',
    'persona.leon_ardis': 'LA',
    'persona.elina_veil': 'EV',
    'persona.kassien_veir': 'KW',
}


class PersonaStopHud:
    def __init__(self, parent, gate, *, physical_stop, resume, reduced_motion: bool = False):
        if not callable(physical_stop) or not callable(resume):
            raise TypeError('hud_callbacks_required')
        self.gate = gate
        self.physical_stop = physical_stop
        self.resume_cb = resume
        self.reduced_motion = bool(reduced_motion)
        self._after_ids: list[str] = []
        self._frozen = False
        self._animating = False
        self.shell = tk.Frame(parent, bg=BG, highlightthickness=1,
                              highlightbackground=LINE, bd=0)
        self.shell.pack(fill='x', padx=4, pady=(8, 4))
        head = tk.Frame(self.shell, bg=BG)
        head.pack(fill='x', padx=8, pady=(8, 2))
        tk.Label(head, text='NOX · PERSONA', fg=AMBER, bg=BG,
                 font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.chips: dict[str, tk.Label] = {}
        for key in ('input', 'ai', 'state'):
            label = tk.Label(head, text='—', fg=INK, bg=CYAN,
                             font=('Segoe UI', 8, 'bold'), padx=6, pady=1)
            label.pack(side='right', padx=2)
            self.chips[key] = label
        self.canvas = tk.Canvas(self.shell, height=54, bg=GLASS,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill='x', padx=8, pady=4)
        self.canvas.bind('<Configure>', lambda _event: self._draw_personas(animate=False))
        self.name = tk.Label(self.shell, text='', fg=TEXT, bg=BG,
                             font=('Segoe UI', 9), anchor='w')
        self.name.pack(fill='x', padx=8)
        self.history = tk.Listbox(self.shell, height=4, bg='#0C141C', fg=TEXT,
                                  selectbackground='#1E3A40', selectforeground=TEXT,
                                  highlightthickness=1, highlightbackground=LINE,
                                  activestyle='none', font=('Consolas', 9),
                                  exportselection=False)
        self.history.pack(fill='x', padx=8, pady=4)
        composer = tk.Frame(self.shell, bg=BG)
        composer.pack(fill='x', padx=8, pady=(0, 4))
        self.entry = tk.Entry(composer, bg='#0E1720', fg=TEXT, insertbackground=CYAN,
                              disabledbackground='#0E1720', disabledforeground=MUTED,
                              relief='flat', highlightthickness=1,
                              highlightbackground=LINE, highlightcolor=CYAN)
        self.entry.pack(side='left', fill='x', expand=True)
        self.send_button = tk.Button(
            composer, text='В ИСТОРИЮ', command=self._record, bg=AMBER, fg=INK,
            activebackground='#F5CEA0', relief='flat', padx=8, pady=2)
        self.send_button.pack(side='left', padx=(6, 0))
        memory = tk.Frame(self.shell, bg=BG)
        memory.pack(fill='x', padx=8, pady=(0, 4))
        self.memory_entry = tk.Entry(memory, bg='#0E1720', fg=TEXT, insertbackground=CYAN,
                                     disabledbackground='#0E1720', disabledforeground=MUTED,
                                     relief='flat', highlightthickness=1,
                                     highlightbackground=LINE)
        self.memory_entry.pack(side='left', fill='x', expand=True)
        self.memory_button = tk.Button(
            memory, text='ПАМЯТЬ', command=self._remember, bg=CYAN, fg=INK,
            activebackground='#7FF3EA', relief='flat', padx=8, pady=2)
        self.memory_button.pack(side='left', padx=(6, 0))
        actions = tk.Frame(self.shell, bg=BG)
        actions.pack(fill='x', padx=8, pady=(0, 8))
        self.stop_button = tk.Button(
            actions, text='STOP', command=self._stop, bg=HALT, fg='#FFF6F2',
            activebackground='#FF8A74', relief='flat', padx=14, pady=4,
            font=('Segoe UI', 10, 'bold'))
        self.stop_button.pack(side='left')
        self.resume_button = tk.Button(
            actions, text='RESUME', command=self._resume, bg='#1C2C36', fg=MUTED,
            activebackground='#27404C', relief='flat', padx=10, pady=4,
            state='disabled')
        self.resume_button.pack(side='left', padx=6)
        self.halt_banner = tk.Label(actions, text='', fg=HALT, bg=BG,
                                    font=('Segoe UI', 9, 'bold'))
        self.halt_banner.pack(side='left', padx=4)
        self._nodes: dict[str, int] = {}
        self._highlight = None
        self._draw_personas(animate=False)
        self.refresh()

    def shutdown(self) -> None:
        self._frozen = True
        self._cancel_after()

    def _cancel_after(self) -> None:
        for token in list(self._after_ids):
            try:
                self.shell.after_cancel(token)
            except tk.TclError:
                pass
        self._after_ids.clear()

    def _later(self, ms: int, callback) -> None:
        if self._frozen:
            return
        try:
            token = self.shell.after(ms, callback)
        except tk.TclError:
            return
        self._after_ids.append(token)

    def refresh(self) -> None:
        chips = self.gate.chips()
        colors = {
            'HALTED': HALT,
            'IN_FLIGHT': AMBER,
            'READY': OK,
            'HOLD': MUTED,
            'NOT_LIVE': '#8AA0A8',
            'LOCAL_REPLY': CYAN,
            'ENABLED': OK,
            'DISABLED': HALT,
        }
        for key in ('state', 'ai', 'input'):
            value = str(chips[key])
            self.chips[key].configure(text=value, bg=colors.get(value, CYAN),
                                      fg=INK if value not in ('NOT_LIVE',) else TEXT)
        persona = get_persona(chips['persona_id'])
        self.name.configure(
            text=f"{persona.display_name}  ·  {persona.persona_id}  ·  history {chips['history_count']}")
        enabled = chips['input'] == 'ENABLED' and not chips['halted']
        entry_state = 'normal' if enabled else 'disabled'
        self.entry.configure(state=entry_state)
        self.memory_entry.configure(state=entry_state)
        self.send_button.configure(state='normal' if enabled else 'disabled')
        self.memory_button.configure(state='normal' if enabled else 'disabled')
        self.resume_button.configure(state='normal' if chips['halted'] else 'disabled',
                                     fg=TEXT if chips['halted'] else MUTED)
        self._fill_history(persona.persona_id)
        if chips['halted']:
            self.halt_banner.configure(text='HALTED')
            self.shell.configure(highlightbackground=HALT)
        elif chips['state'] == 'IN_FLIGHT':
            self.halt_banner.configure(text='IN FLIGHT')
            self.shell.configure(highlightbackground=AMBER)
        else:
            self.halt_banner.configure(text='')
            self.shell.configure(highlightbackground=LINE)

    def _fill_history(self, persona_id: str) -> None:
        rows = self.gate.buckets.history(persona_id)
        self.history.delete(0, 'end')
        if not rows:
            self.history.insert('end', '— пусто для этой персоны —')
            return
        for row in rows[-12:]:
            self.history.insert('end', f"{row['role']}: {row['body']}")

    def _draw_personas(self, *, animate: bool) -> None:
        try:
            width = max(int(self.canvas.winfo_width()), 280)
        except tk.TclError:
            return
        self.canvas.delete('persona')
        count = len(PERSONAS)
        gap = width / count
        current = self.gate.chips()['persona_id']
        self._nodes.clear()
        for index, persona in enumerate(PERSONAS):
            cx = gap * index + gap / 2
            color = ACCENT[persona.persona_id]
            node = self.canvas.create_oval(cx - 14, 12, cx + 14, 40, fill=GLASS,
                                           outline=color, width=2, tags='persona')
            self.canvas.create_text(cx, 26, text=CODE[persona.persona_id],
                                    fill=color, font=('Segoe UI', 8, 'bold'), tags='persona')
            self._nodes[persona.persona_id] = node
            self.canvas.tag_bind(node, '<Button-1>',
                                 lambda _event, pid=persona.persona_id: self._select(pid))
        target = self._nodes.get(current)
        if target is None:
            return
        box = self.canvas.bbox(target)
        if self._highlight is None:
            self._highlight = self.canvas.create_rectangle(
                box, outline=CYAN, width=2, tags='persona')
        else:
            if animate and not self.reduced_motion and not self._frozen:
                self._slide_highlight(self.canvas.coords(self._highlight), box, step=0)
            else:
                self.canvas.coords(self._highlight, box)

    def _slide_highlight(self, start, end, *, step: int) -> None:
        if self._frozen or self.gate.chips()['halted']:
            return
        steps = 7
        mix = min(step, steps) / steps
        coords = [start[i] + (end[i] - start[i]) * mix for i in range(4)]
        try:
            self.canvas.coords(self._highlight, coords)
        except tk.TclError:
            return
        if step < steps:
            self._later(16, lambda: self._slide_highlight(start, end, step=step + 1))

    def animate_to(self, persona_id: str) -> None:
        if self._frozen:
            return
        self.refresh()
        self._draw_personas(animate=not self.gate.chips()['halted'])

    def _select(self, persona_id: str) -> None:
        if self.gate.chips()['halted']:
            self.refresh()
            return
        self.gate.switch_persona(persona_id)
        self.animate_to(persona_id)

    def _record(self) -> None:
        text = self.entry.get()
        try:
            self.gate.record_user(self.gate.chips()['persona_id'], text)
        except (PermissionError, ValueError):
            self.refresh()
            return
        self.entry.delete(0, 'end')
        self.refresh()

    def _remember(self) -> None:
        text = self.memory_entry.get()
        try:
            self.gate.remember(self.gate.chips()['persona_id'], text)
        except (PermissionError, ValueError):
            self.refresh()
            return
        self.memory_entry.delete(0, 'end')
        self.refresh()

    def _stop(self) -> None:
        self.physical_stop()

    def _resume(self) -> None:
        try:
            self.resume_cb()
        except PermissionError:
            self.refresh()
            return
        self._frozen = False
        self.show_ready()

    def show_halted(self) -> None:
        """Flash the STOP frame, then freeze motion and input."""
        self._cancel_after()
        self.refresh()
        if self.reduced_motion:
            self._freeze()
            return
        self._flash(0)

    def _flash(self, step: int) -> None:
        if self._frozen and step > 0:
            return
        color = HALT if step % 2 == 0 else AMBER
        try:
            self.shell.configure(highlightbackground=color, highlightthickness=2)
            self.stop_button.configure(bg=color)
        except tk.TclError:
            return
        if step >= 5:
            self._freeze()
            return
        self._later(70, lambda: self._flash(step + 1))

    def _freeze(self) -> None:
        self._cancel_after()
        try:
            self.shell.configure(highlightbackground=HALT, highlightthickness=2)
            self.stop_button.configure(bg=HALT)
            self.halt_banner.configure(text='HALTED')
        except tk.TclError:
            return
        self.refresh()

    def show_ready(self) -> None:
        self._cancel_after()
        try:
            self.shell.configure(highlightthickness=1)
            self.stop_button.configure(bg=HALT)
        except tk.TclError:
            return
        self.refresh()
        self._draw_personas(animate=True)
