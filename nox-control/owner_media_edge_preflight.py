"""Read-only source and endpoint gate for the staged Resonance media release."""

import ast
from hashlib import sha256

from attach_resonance_media_edge import PAGE_BY_EDGE, attach_media_edge


BACKEND_PIN = "48c89a84f7c1c701e275062fb54a9595317a13eb8bdd5c83492fb5cbd1eeb224"
BUILD_BY_EDGE = {
    "4dfc48d178de35c1ba3b6625fd2cd7e2df891b3dac6c515947971e4863a97eeb": (
        "b302d299de6560248550853ef02b2120457d6897325053ff6913d2f151bd823c",
        "67db8e3f9a928199c8b256bd12e0cc01efd7be39af94bdc73ff052d5e4b95ddf",
    ),
    "6697fd91f95d951815ba46f3bc619151499e767c297d8a358cc815aeb03a136e": (
        "6a09e4fff48dcd4d38658ed33d7c3c773a5e345a749ead538a94c032f6a0b1c4",
        "9ada781573227d43016331fe62202d2cc33cb369c49a978185d0a915a7ca10cf",
    ),
}
MEDIA = "/api/ui/media"
RAM_FLOORS = {"image": 16 << 30, "video": 24 << 30}
GPU_FLOOR_MIB = 30000
DISK_FLOOR = 6 << 30


class MediaActivationHold(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise MediaActivationHold("HOLD_MEDIA_EDGE_" + reason)


def preflight(*, edge, backend, script, style, request, resources):
    """The owner transport supplies pinned bytes, local HTTP and current counters.

    request(path, authenticated=...) must make bounded GETs through the existing
    owner transport. No POST, process lifecycle call or file write is made here.
    """
    require(sha256(backend).hexdigest() == BACKEND_PIN, "NATIVE_BACKEND_PIN")
    edge_pin = sha256(edge).hexdigest()
    build = BUILD_BY_EDGE.get(edge_pin)
    require(build is not None, "SOURCE_BUILD_PIN")
    candidate_pin, candidate_page_pin = build
    candidate = attach_media_edge(edge, script, style)
    require(sha256(candidate).hexdigest() == candidate_pin, "CANDIDATE_PIN")

    status, page = request("/chat", authenticated=False)
    require(status == 200 and type(page) is bytes and sha256(page).hexdigest() == PAGE_BY_EDGE[edge_pin],
            "SERVING_PAGE_PIN")
    for path in (MEDIA, MEDIA + "/requests/" + "0" * 32, MEDIA + "/jobs/" + "0" * 32 + "/outputs/0"):
        status, _ = request(path, authenticated=False)
        require(status in (401, 403), "NATIVE_AUTH_BOUNDARY")
    status, capability = request(MEDIA, authenticated=True)
    require(status == 200 and type(capability) is dict
            and capability.get("schema") == "NOX_OWNER_MEDIA_V1"
            and capability.get("idempotency_v1") is True
            and capability.get("backend") == "EXISTING_NOX_DISPATCHER_COMFYUI",
            "NATIVE_API_CONTRACT")
    require(type(resources) is dict and resources.get("stop_active") is False
            and resources.get("media_queue_idle") is True, "STOP_OR_ACTIVE_MEDIA")
    counters = ("raw_cgroup_headroom_bytes", "gpu1_free_mib", "output_disk_free_bytes",
                "configured_cgroup_reserve_bytes", "configured_output_disk_reserve_bytes")
    require(all(type(resources.get(key)) is int and resources[key] >= 0 for key in counters),
            "RESOURCE_COUNTERS")
    kinds = tuple(kind for kind, floor in RAM_FLOORS.items()
                  if (capability.get(kind) is True and resources["raw_cgroup_headroom_bytes"]
                      >= max(floor, resources["configured_cgroup_reserve_bytes"])
                      and resources["gpu1_free_mib"] >= GPU_FLOOR_MIB
                      and resources["output_disk_free_bytes"]
                      >= max(DISK_FLOOR, resources["configured_output_disk_reserve_bytes"])))
    require(bool(kinds), "NO_KIND_READY_FOR_ACTIVATION")
    assignment = next(node for node in ast.parse(candidate).body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "PAGE" for target in node.targets))
    new_page = ast.literal_eval(assignment.value)
    require(sha256(new_page).hexdigest() == candidate_page_pin, "CANDIDATE_PAGE_PIN")
    return candidate, {"candidate_sha256": candidate_pin, "page_sha256": candidate_page_pin,
                       "available_kinds": kinds, "generation_started": False, "host_writes": 0}
