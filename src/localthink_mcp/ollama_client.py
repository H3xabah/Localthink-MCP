import httpx
import os

BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")
# OLLAMA_FAST_MODEL: lightweight model for classify/code_surface/outline.
# Falls back to DEFAULT_MODEL if unset.
FAST_MODEL = os.environ.get("OLLAMA_FAST_MODEL", "") or DEFAULT_MODEL


def health_check(timeout: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def generate(prompt: str, system: str = "", model: str = "", timeout: float = 120.0) -> str:
    payload: dict = {
        "model": model or DEFAULT_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{BASE_URL}/api/generate", json=payload)
        r.raise_for_status()
        return r.json()["response"]


def generate_fast(prompt: str, system: str = "", timeout: float = 60.0) -> str:
    """Use the fast model for lightweight ops: classify, outline, code_surface (non-Python)."""
    return generate(prompt=prompt, system=system, model=FAST_MODEL, timeout=timeout)


def list_models() -> list[str]:
    """Return names of all locally available Ollama models."""
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{BASE_URL}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
