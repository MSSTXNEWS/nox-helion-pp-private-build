"""Headless-capable M2.3 receipt. Runs inside a built executable when frozen.

The scenarios use a stub callback, never a model. live_ai is always false.
Screenshots are recorded only when an OS window bitmap is actually captured.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

from helion.m23_persona_stop import TurnGate, legacy_shared_transcript
from helion.personas import PERSONAS

REFERENCE_EXE_SHA256 = '93a329ba1ece9cfd66951b377e04e9c1166ec6ba3ce13a5911ba8e36de99dfb8'
P1 = PERSONAS[0].persona_id
P2 = PERSONAS[1].persona_id


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _logic(data_dir: Path) -> dict:
    evidence = {'checks': [], 'live_ai': False}
    store_path = data_dir / 'm23_persona_buckets.sqlite3'

    shared = []
    shared.append({'persona_id': P1, 'body': 'ALPHA_SECRET'})
    shared.append({'persona_id': P2, 'body': 'BETA_SECRET'})
    leaked = legacy_shared_transcript(shared, P1)
    shared_leaks = any(row['body'] == 'BETA_SECRET' for row in leaked)
    evidence['checks'].append({
        'name': 'old_shared_list_failure_mode',
        'shared_list_leaks': shared_leaks,
    })

    gate = TurnGate(store_path)
    gate.switch_persona(P1)
    gate.record_user(P1, 'ALPHA_SECRET')
    gate.remember(P1, 'MEMORY_ALPHA')
    generation = gate.begin_turn(P1, 'ALPHA_QUESTION')
    committed = gate.try_commit_assistant(
        P1, 'ALPHA_REPLY', generation, source='stub_callback_not_live_ai')
    gate.switch_persona(P2)
    gate.record_user(P2, 'BETA_SECRET')
    visible = [row['body'] for row in gate.buckets.history(P2)]
    hidden = [row['body'] for row in gate.buckets.history(P1)]
    isolation_ok = (
        shared_leaks and committed and 'BETA_SECRET' in visible
        and 'ALPHA_SECRET' not in visible and 'BETA_SECRET' not in hidden
        and 'MEMORY_ALPHA' not in visible)
    try:
        gate.record_user(P1, 'SHOULD_NOT_LAND_IN_OTHER')
        cross_write = True
    except PermissionError:
        cross_write = False
    isolation_ok = isolation_ok and not cross_write
    evidence['checks'].append({
        'name': 'persona_isolation',
        'pass': isolation_ok,
        'cross_write_blocked': not cross_write,
        'visible_persona': P2,
        'visible_bodies': visible,
    })

    restarted = TurnGate(store_path)
    restarted.switch_persona(P1)
    again = [row['body'] for row in restarted.buckets.history(P1)]
    other = [row['body'] for row in restarted.buckets.history(P2)]
    restart_ok = 'ALPHA_SECRET' in again and 'BETA_SECRET' not in again and 'BETA_SECRET' in other
    evidence['checks'].append({'name': 'restart_persistence', 'pass': restart_ok})

    stop_gate = TurnGate(data_dir / 'm23_stop.sqlite3')
    stop_gate.switch_persona(P1)
    inflight = stop_gate.begin_turn(P1, 'IN_FLIGHT_QUESTION')
    receipt = stop_gate.halt()
    late = stop_gate.try_commit_assistant(
        P1, 'LATE_SECRET', inflight, source='stub_callback_not_live_ai')
    try:
        stop_gate.record_user(P1, 'BLOCKED_SEND')
        send_blocked = False
    except PermissionError as exc:
        send_blocked = str(exc) == 'stop_blocks_send'
    bodies = [row['body'] for row in stop_gate.buckets.history(P1)]
    late_ok = (late is False and 'LATE_SECRET' not in bodies
               and 'IN_FLIGHT_QUESTION' in bodies and receipt['state'] == 'HALTED'
               and stop_gate.inflight is None)
    evidence['checks'].append({
        'name': 'stop_blocks_send',
        'pass': send_blocked,
    })
    evidence['checks'].append({
        'name': 'inflight_cancel',
        'pass': receipt['cancelled_generation'] == inflight and stop_gate.inflight is None,
    })
    evidence['checks'].append({
        'name': 'late_write_forbidden',
        'pass': late_ok,
        'appended': 'LATE_SECRET' in bodies,
        'late_rejects': stop_gate.late_rejects,
    })
    resumed = stop_gate.resume()
    ready = stop_gate.chips()
    resumed_gen = stop_gate.begin_turn(P1, 'AFTER_RESUME')
    resume_ok = (resumed['input'] == 'ENABLED' and resumed['state'] == 'READY'
                 and ready['state'] == 'READY' and ready['input'] == 'ENABLED'
                 and resumed_gen > 0 and ready['ai'] == 'NOT_LIVE'
                 and ready['live_ai'] is False)
    evidence['checks'].append({'name': 'resume', 'pass': resume_ok, 'chips': ready})
    evidence['logic_pass'] = bool(
        shared_leaks and isolation_ok and restart_ok and send_blocked
        and late_ok and resume_ok and receipt['cancelled_generation'] == inflight)
    return evidence


def _capture_bitmap(widget, path: Path) -> dict:
    """Capture the real window bitmap. Failure stays NOT_CAPTURED."""
    result = {'captured': False, 'reason': 'NOT_ATTEMPTED', 'path': str(path),
              'bytes': 0, 'sha256': None}
    try:
        widget.update_idletasks()
        widget.update()
    except Exception as exc:
        result['reason'] = 'widget_update_failed:' + type(exc).__name__
        return result
    if sys.platform == 'win32':
        return _capture_windows(widget, path, result)
    return _capture_pil(widget, path, result)


def _capture_pil(widget, path: Path, result: dict) -> dict:
    try:
        from PIL import ImageGrab
    except Exception as exc:
        result['reason'] = 'screenshot_backend_unavailable:' + type(exc).__name__
        return result
    try:
        x = int(widget.winfo_rootx())
        y = int(widget.winfo_rooty())
        w = int(widget.winfo_width())
        h = int(widget.winfo_height())
        if w < 20 or h < 20:
            result['reason'] = 'window_too_small'
            return result
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, 'PNG')
    except Exception as exc:
        result['reason'] = 'ImageGrab_failed:' + type(exc).__name__
        return result
    digest = _sha256_file(path)
    size = path.stat().st_size if path.is_file() else 0
    if not digest or size < 64:
        result['reason'] = 'screenshot_file_empty'
        return result
    result.update(captured=True, reason='ImageGrab', bytes=size, sha256=digest)
    return result


def _capture_windows(widget, path: Path, result: dict) -> dict:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
    hwnd = int(widget.winfo_id())
    root = user32.GetAncestor(hwnd, 2) or hwnd
    rect = wintypes.RECT()
    if not user32.GetWindowRect(root, ctypes.byref(rect)):
        result['reason'] = 'GetWindowRect_failed'
        return result
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width < 20 or height < 20 or width > 8000 or height > 8000:
        result['reason'] = f'window_bounds_{width}x{height}'
        return result
    hdc = user32.GetWindowDC(root)
    if not hdc:
        result['reason'] = 'GetWindowDC_failed'
        return result
    try:
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
        if not mem or not bmp:
            result['reason'] = 'compatible_bitmap_failed'
            return result
        old = gdi32.SelectObject(mem, bmp)
        copied = gdi32.BitBlt(mem, 0, 0, width, height, hdc, 0, 0, 0x00CC0020)
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG), ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)]
        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = height
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0
        stride = width * 4
        buffer = ctypes.create_string_buffer(stride * height)
        lines = gdi32.GetDIBits(mem, bmp, 0, height, buffer, ctypes.byref(header), 0)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        if not copied or lines == 0:
            result['reason'] = 'GetDIBits_failed'
            return result
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_bmp(path, width, height, buffer.raw)
    except Exception as exc:
        result['reason'] = 'gdi_capture_failed:' + type(exc).__name__
        return result
    finally:
        user32.ReleaseDC(root, hdc)
    digest = _sha256_file(path)
    size = path.stat().st_size if path.is_file() else 0
    if not digest or size < 64:
        result['reason'] = 'screenshot_file_empty'
        return result
    result.update(captured=True, reason='Windows_GDI', bytes=size, sha256=digest)
    return result


def _write_bmp(path: Path, width: int, height: int, raw: bytes) -> None:
    stride = width * 4
    pixel_size = stride * height
    offset = 14 + 40
    file_size = offset + pixel_size
    header = b'BM' + file_size.to_bytes(4, 'little') + (0).to_bytes(4, 'little')
    header += offset.to_bytes(4, 'little')
    info = (40).to_bytes(4, 'little') + width.to_bytes(4, 'little', signed=True)
    info += height.to_bytes(4, 'little', signed=True) + (1).to_bytes(2, 'little')
    info += (32).to_bytes(2, 'little') + (0).to_bytes(4, 'little')
    info += pixel_size.to_bytes(4, 'little') + (0).to_bytes(16, 'little')
    path.write_bytes(header + info + raw[:pixel_size])


def _gui(data_dir: Path, screenshot_dir: Path | None) -> dict:
    report = {
        'exercised': False,
        'display': False,
        'persona_switch': False,
        'stop_button': False,
        'alt_s': False,
        'late_write_appended': None,
        'resume': False,
        'chips_match_gate': False,
        'screenshots': [],
        'error': None,
        'live_ai': False,
    }
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as exc:
        report['error'] = 'display_unavailable:' + type(exc).__name__
        return report
    try:
        from helion.m23_hud import PersonaStopHud
        root.title('NOX HELION · M2.3 persona / STOP')
        root.geometry('560x420+80+60')
        root.configure(bg='#070B10')
        gate = TurnGate(data_dir / 'm23_hud.sqlite3')
        holder = {'hud': None}

        def physical():
            gate.halt()
            hud = holder['hud']
            if hud is not None:
                hud.show_halted()

        def resume():
            gate.resume()
            hud = holder['hud']
            if hud is not None:
                hud.show_ready()

        hud = PersonaStopHud(root, gate, physical_stop=physical, resume=resume,
                             reduced_motion=True)
        holder['hud'] = hud
        root.bind('<Alt-s>', lambda _event: physical())
        root.bind('<Alt-S>', lambda _event: physical())
        report['display'] = True
        gate.switch_persona(P1)
        hud.entry.configure(state='normal')
        hud.entry.insert(0, 'HUD_ALPHA')
        hud._record()
        gate.switch_persona(P2)
        hud.animate_to(P2)
        hud.entry.configure(state='normal')
        hud.entry.delete(0, 'end')
        hud.entry.insert(0, 'HUD_BETA')
        hud._record()
        root.update()
        shown = list(hud.history.get(0, 'end'))
        report['persona_switch'] = (
            any(line.startswith('user: HUD_BETA') for line in shown)
            and all('HUD_ALPHA' not in line for line in shown))
        generation = gate.begin_turn(P2, 'HUD_IN_FLIGHT')
        hud.refresh()
        chips_before = gate.chips()
        report['chips_match_gate'] = (
            hud.chips['state'].cget('text') == chips_before['state']
            and hud.chips['ai'].cget('text') == 'NOT_LIVE'
            and chips_before['live_ai'] is False)
        hud.stop_button.invoke()
        root.update()
        late = gate.try_commit_assistant(
            P2, 'HUD_LATE_SECRET', generation, source='stub_callback_not_live_ai')
        bodies = [row['body'] for row in gate.buckets.history(P2)]
        report['stop_button'] = gate.halted and gate.chips()['state'] == 'HALTED'
        report['late_write_appended'] = late is True or 'HUD_LATE_SECRET' in bodies
        gate2 = TurnGate(data_dir / 'm23_alt.sqlite3')
        holder2 = {'hud': None}

        def physical2():
            gate2.halt()
            if holder2['hud'] is not None:
                holder2['hud'].show_halted()

        # Alt+S is bound on the same root; point it at a fresh gate by rebinding.
        root.bind('<Alt-s>', lambda _event: physical2())
        root.bind('<Alt-S>', lambda _event: physical2())
        gate2.switch_persona(P1)
        alt_gen = gate2.begin_turn(P1, 'ALT_QUESTION')
        root.focus_force()
        root.event_generate('<Alt-s>')
        root.update()
        alt_late = gate2.try_commit_assistant(
            P1, 'ALT_LATE_SECRET', alt_gen, source='stub_callback_not_live_ai')
        report['alt_s'] = (gate2.halted and alt_late is False
                           and 'ALT_LATE_SECRET' not in
                           [row['body'] for row in gate2.buckets.history(P1)])
        hud.resume_button.configure(state='normal')
        # Resume the first gate through its own button after rebinding resume.
        gate_was_halted = gate.halted
        if gate_was_halted:
            hud.resume_button.invoke()
        root.update()
        report['resume'] = (not gate.halted and gate.input_enabled
                            and hud.entry.cget('state') == 'normal')
        report['exercised'] = True
        if screenshot_dir is not None:
            shot = screenshot_dir / ('m23-hud-halted.bmp' if sys.platform == 'win32'
                                     else 'm23-hud-halted.png')
            # Leave the window in HALTED so the bitmap matches the STOP state.
            physical()
            root.update()
            report['screenshots'].append(_capture_bitmap(root, shot))
        hud.shutdown()
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)[:300]
        report['traceback'] = traceback.format_exc()[-1200:]
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    return report


def _shell_probe(data_dir: Path) -> dict:
    """Open the real E08 shell inside this process when the host asks for it.

    The import is dynamic so the smaller Linux self-test binary does not have
    to bundle the whole desktop. A missing module is recorded, not invented.
    """
    report = {'attempted': False, 'pass': False, 'reason': 'not_requested', 'live_ai': False}
    if os.environ.get('NOX_M23_PROBE_SHELL') != '1':
        return report
    report['attempted'] = True
    root = None
    try:
        import importlib
        import tkinter as tk
        e08 = importlib.import_module('helion.e08_desktop_ui')
        app = importlib.import_module('helion.app')
        storage = importlib.import_module('helion.storage')
        root = tk.Tk()
        shell_dir = data_dir / 'shell-probe'
        shell_dir.mkdir(parents=True, exist_ok=True)
        store = storage.Store(shell_dir / 'helion.sqlite3')
        ui = e08.E08Desktop(root, store, app.build_routes(store), data_dir=shell_dir)
        root.update()
        persona = ui.persona.get()
        generation = int(ui._poll_generation) + 1
        ui.m23_gate.arm_inflight(persona, generation)
        ui.m23_physical_stop()
        root.update()
        late = ui.m23_gate.try_commit_assistant(
            persona, 'SHELL_LATE', generation, source='stub_callback_not_live_ai')
        halted = bool(ui.m23_gate.halted and ui.m23_hud.chips['state'].cget('text') == 'HALTED')
        ai_chip = ui.m23_hud.chips['ai'].cget('text')
        ui.m23_resume()
        root.update()
        ui.m23_gate.record_user(persona, 'SHELL_ALPHA')
        other = next(item.persona_id for item in PERSONAS if item.persona_id != persona)
        ui.persona.set(other)
        root.update()
        shown = list(ui.m23_hud.history.get(0, 'end'))
        isolated = all('SHELL_ALPHA' not in line for line in shown)
        root.focus_force()
        root.update()
        ui.m23_gate.arm_inflight(other, int(ui._poll_generation) + 3)
        root.event_generate('<Alt-s>')
        root.update()
        alt = bool(ui.m23_gate.halted and ui.m23_gate.inflight is None)
        try:
            ui.close()
        except Exception:
            pass
        store.close()
        report.update({
            'pass': bool(halted and ai_chip == 'NOT_LIVE' and late is False and isolated and alt),
            'halted': halted,
            'ai_chip': ai_chip,
            'late_appended': late is True,
            'isolated': isolated,
            'alt_s': alt,
            'reason': None,
        })
    except Exception as exc:
        report['reason'] = type(exc).__name__ + ': ' + str(exc)[:400]
        report['traceback'] = traceback.format_exc()[-1500:]
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    return report


def build_receipt(data_dir: Path, screenshot_dir: Path | None) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    logic = _logic(data_dir)
    gui = _gui(data_dir, screenshot_dir)
    shell = _shell_probe(data_dir)
    frozen = bool(getattr(sys, 'frozen', False))
    executable = Path(sys.executable)
    own_sha = _sha256_file(executable) if frozen else None
    screenshot_proven = any(item.get('captured') is True for item in gui['screenshots'])
    logic_pass = bool(logic['logic_pass'])
    gui_pass = bool(gui['exercised'] and gui['persona_switch'] and gui['stop_button']
                    and gui['alt_s'] and gui['resume'] and gui['late_write_appended'] is False
                    and gui['chips_match_gate'])
    shell_pass = shell.get('pass') is True
    if not logic_pass:
        overall = 'LOGIC_FAIL'
    elif frozen and gui_pass and shell_pass and screenshot_proven:
        overall = 'EXE_LOGIC_HUD_AND_SHELL_PASS_WITH_SCREENSHOT'
    elif frozen and gui_pass and shell_pass:
        overall = 'EXE_LOGIC_HUD_AND_SHELL_PASS_SCREENSHOT_NOT_CAPTURED'
    elif frozen and gui_pass and screenshot_proven:
        overall = 'EXE_LOGIC_AND_HUD_PASS_WITH_SCREENSHOT'
    elif frozen and gui_pass:
        overall = 'EXE_LOGIC_AND_HUD_PASS_SCREENSHOT_NOT_CAPTURED'
    elif frozen:
        overall = 'EXE_LOGIC_PASS_HUD_NOT_PROVEN'
    elif gui_pass and shell_pass:
        overall = 'SOURCE_LOGIC_HUD_AND_SHELL_PASS_NOT_AN_EXE'
    elif gui_pass:
        overall = 'SOURCE_LOGIC_AND_HUD_PASS_NOT_AN_EXE'
    else:
        overall = 'SOURCE_LOGIC_PASS_HUD_NOT_PROVEN_NOT_AN_EXE'
    not_proven = [
        'Live model inference was not run and is not claimed.',
        'Reference EXE sha256 ' + REFERENCE_EXE_SHA256 + ' was not executed or modified.',
    ]
    if not frozen:
        not_proven.append('This process is not a frozen executable, so it is not EXE evidence.')
    if not screenshot_proven:
        not_proven.append('No OS window bitmap was captured.')
    if not gui_pass:
        not_proven.append('The Tk HUD scenario did not fully pass in this process.')
    if not shell_pass:
        not_proven.append('The full E08 desktop shell was not proven inside this process.')
    return {
        'schema': 'NOX_M23_PERSONA_STOP_EXE_RECEIPT_V1',
        'milestone': 'M2.3',
        'item': 6,
        'live_ai': False,
        'ai_status': 'NOT_LIVE',
        'overall': overall,
        'logic_pass': logic_pass,
        'hud_pass': gui_pass,
        'frozen_executable': frozen,
        'executable': str(executable),
        'argv0': sys.argv[0],
        'this_binary_sha256': own_sha,
        'reference_exe_sha256': REFERENCE_EXE_SHA256,
        'reference_exe_executed': False,
        'reference_exe_modified': False,
        'reference_sha_matches_this_binary': own_sha == REFERENCE_EXE_SHA256,
        'platform': sys.platform,
        'python': sys.version,
        'logic': logic,
        'gui': gui,
        'shell_probe': shell,
        'screenshot_proven': screenshot_proven,
        'not_proven': not_proven,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='NOX M2.3 persona/STOP self-test')
    parser.add_argument('--m23-self-test', action='store_true')
    parser.add_argument('--m23-receipt', type=Path, required=True)
    parser.add_argument('--m23-screenshot-dir', type=Path)
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = build_receipt(args.data_dir, args.m23_screenshot_dir)
    args.m23_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.m23_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
    print(json.dumps({'overall': receipt['overall'], 'logic_pass': receipt['logic_pass'],
                      'hud_pass': receipt['hud_pass'], 'live_ai': False,
                      'screenshot_proven': receipt['screenshot_proven'],
                      'frozen_executable': receipt['frozen_executable']},
                     ensure_ascii=False))
    return 0 if receipt['logic_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
