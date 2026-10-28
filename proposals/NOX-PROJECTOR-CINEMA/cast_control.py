"""NOX Cinema / Google Cast, using existing optional PyChromecast library.
All network actions require explicit user approval in the trusted native host.
No private device discovery or playback on import; no second AI backend.
"""
from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
import math

from cast_gateway import LocalCastGateway, MediaHold, checked_lan_ip

class CastHold(MediaHold):
    pass

@dataclass(frozen=True)
class CastDevice:
    id: str
    name: str
    host: str
    model: str
    kind: str

class ProjectorCastController:
    def __init__(self, *, cast_api=None, gateway_factory=LocalCastGateway):
        self._cast_api = cast_api
        self._gateway_factory = gateway_factory
        self._devices = {}
        self._selected = None
        self._gateway = None
        self._state = "DISCONNECTED"

    def _api(self):
        if self._cast_api is not None:
            return self._cast_api
        try:
            import pychromecast
        except ImportError as exc:
            raise CastHold("OPTIONAL_PYCHROMECAST_NOT_INSTALLED") from exc
        return pychromecast

    def discover(self, *, user_approved: bool):
        if user_approved is not True:
            raise CastHold("DISCOVERY_REQUIRES_USER_ACTION")
        api = self._api()
        discovered, browser = api.get_chromecasts(timeout=5)
        try:
            items = {}
            for cast in discovered:
                info = cast.cast_info
                uuid = str(info.uuid)
                try:
                    host = checked_lan_ip(info.host)
                except MediaHold:
                    continue
                if info.cast_type in ("audio","group"):
                    continue
                if not info.friendly_name or len(info.friendly_name) > 120:
                    continue
                # UUID from mDNS is the selector; never use a caller-chosen IP/hostname.
                try:
                    UUID(uuid)
                except ValueError:
                    continue
                items[uuid] = cast
            self._devices = items
            return [CastDevice(id=key,name=str(cc.cast_info.friendly_name),
                host=str(cc.cast_info.host),model=str(cc.cast_info.model_name or ""),
                kind=str(cc.cast_info.cast_type or "unknown")) for key,cc in items.items()]
        finally:
            browser.stop_discovery()

    def select(self, device_id: str, *, user_approved: bool):
        if user_approved is not True:
            raise CastHold("PROJECTOR_SELECTION_REQUIRES_CONFIRMATION")
        if not isinstance(device_id,str) or device_id not in self._devices:
            raise CastHold("PROJECTOR_NOT_DISCOVERED")
        self.stop()
        self._selected = device_id
        self._state = "SELECTED_NOT_PLAYING"
        info = self._devices[device_id].cast_info
        return CastDevice(id=device_id,name=info.friendly_name,
            host=info.host,model=str(info.model_name or ""),kind=str(info.cast_type or "unknown"))

    def start_movie(self, *, movie_path, library_root, local_lan_ip: str,
                    user_approved: bool, rights_confirmed: bool):
        if user_approved is not True or rights_confirmed is not True:
            raise CastHold("CAST_REQUIRES_EXPLICIT_CONSENT_AND_RIGHTS")
        if self._selected is None or self._selected not in self._devices:
            raise CastHold("PROJECTOR_MUST_BE_SELECTED")
        self.stop(keep_selection=True)
        device = self._devices[self._selected]
        info = device.cast_info
        self._gateway = self._gateway_factory(movie_path,library_root=library_root,
            local_ip=local_lan_ip,device_ip=info.host,rights_confirmed=True)
        try:
            url = self._gateway.start()
            device.wait(timeout=9)
            device.media_controller.play_media(url,self._gateway.mime)
            # Queued request is not evidence that the receiver has started playback.
            self._state = "SENT_TO_CAST_NOT_CONFIRMED_PLAYING"
            return {"status":self._state,"deviceId":self._selected,"format":self._gateway.mime}
        except Exception as exc:
            self._gateway.stop()
            self._gateway = None
            self._state = "CAST_START_FAILED"
            raise CastHold("CAST_START_FAILED") from exc

    def status(self):
        if self._selected is None:
            return {"status":self._state,"deviceId":None,"position":None,"duration":None}
        cast = self._devices[self._selected]
        mc = cast.media_controller
        s = mc.status
        actual = str(getattr(s,"player_state","UNKNOWN") or "UNKNOWN")
        duration = getattr(s,"duration",None)
        position = getattr(s,"current_time",None)
        dur = float(duration) if isinstance(duration,(int,float)) and math.isfinite(duration) else None
        pos = float(position) if isinstance(position,(int,float)) and math.isfinite(position) else None
        return {"status":actual if actual in ("PLAYING","PAUSED","BUFFERING","IDLE") else self._state,
            "deviceId":self._selected,"position":pos,"duration":dur}

    def control(self, action, *, user_approved: bool, position=None):
        if user_approved is not True:
            raise CastHold("MEDIA_CONTROLS_REQUIRE_USER_CONSENT")
        if self._selected is None or self._gateway is None:
            raise CastHold("NO_ACTIVE_CAST_SESSION")
        mc = self._devices[self._selected].media_controller
        if action == "pause":
            mc.pause()
        elif action == "resume":
            mc.play()
        elif action == "stop":
            mc.stop()
            self.stop()
            return {"status":"STOPPED"}
        elif action == "seek":
            if (not isinstance(position,(int,float)) or isinstance(position,bool)
                or not math.isfinite(position) or not 0 <= position <= 86_400):
                raise CastHold("INVALID_SEEK_POSITION")
            mc.seek(float(position))
        else:
            raise CastHold("UNKNOWN_CAST_ACTION")
        return {"status":"COMMAND_SENT_NOT_ACKNOWLEDGED","action":action}

    def stop(self, *, keep_selection=False):
        if self._gateway:
            self._gateway.stop()
            self._gateway = None
        if not keep_selection:
            self._selected = None
        self._state = "DISCONNECTED" if not keep_selection else "SELECTED_NOT_PLAYING"

    def close(self):
        self.stop()
        for device in self._devices.values():
            try:
                device.disconnect(timeout=1)
            except Exception:
                pass
        self._devices.clear()
