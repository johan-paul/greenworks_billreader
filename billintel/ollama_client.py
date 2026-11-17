"""Loopback-only Ollama HTTP client and local-model checks."""

import json
from urllib.request import Request, ProxyHandler, build_opener

BASE_URL = "http://127.0.0.1:11434"


def api(path: str, payload: dict | None = None, timeout: int = 600):
    # No remote host configuration and no environment HTTP proxy for bill data.
    req = Request(
        BASE_URL + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with build_opener(ProxyHandler({})).open(req, timeout=timeout) as response:
        return json.load(response)


def local_models():
    return [m["name"] for m in api("/api/tags", timeout=10)["models"]]


def check_model(model: str, vision: bool = False):
    info = api("/api/show", {"model": model}, timeout=30)
    if "cloud" in model.lower() or info.get("remote_host") or info.get("remote_model"):
        raise ValueError(
            "Cloud models are prohibited. Choose a downloaded local model."
        )
    if vision and "vision" not in info.get("capabilities", []):
        raise ValueError(f"{model} does not advertise vision support.")
