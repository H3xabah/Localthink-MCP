import httpx
import os

BASE_URL      = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")
FAST_MODEL    = os.environ.get("OLLAMA_FAST_MODEL", "") or DEFAULT_MODEL
TINY_MODEL    = os.environ.get("OLLAMA_TINY_MODEL", "") or FAST_MODEL

_T_GENERATE = float(os.environ.get("LOCALTHINK_TIMEOUT",        "360"))
_T_FAST     = float(os.environ.get("LOCALTHINK_FAST_TIMEOUT",   "180"))
_T_TINY     = float(os.environ.get("LOCALTHINK_TINY_TIMEOUT",   "60"))
_T_HEALTH   = float(os.environ.get("LOCALTHINK_HEALTH_TIMEOUT", "2"))


def reload_env() -> None:
    """Re-read all env vars into module globals. Called by config.apply_config()."""
    global BASE_URL, DEFAULT_MODEL, FAST_MODEL, TINY_MODEL
    global _T_GENERATE, _T_FAST, _T_TINY, _T_HEALTH
    BASE_URL      = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")
    FAST_MODEL    = os.environ.get("OLLAMA_FAST_MODEL", "") or DEFAULT_MODEL
    TINY_MODEL    = os.environ.get("OLLAMA_TINY_MODEL", "") or FAST_MODEL
    _T_GENERATE   = float(os.environ.get("LOCALTHINK_TIMEOUT",        "360"))
    _T_FAST       = float(os.environ.get("LOCALTHINK_FAST_TIMEOUT",   "180"))
    _T_TINY       = float(os.environ.get("LOCALTHINK_TINY_TIMEOUT",   "60"))
    _T_HEALTH     = float(os.environ.get("LOCALTHINK_HEALTH_TIMEOUT", "2"))


def health_check(timeout: float | None = None) -> bool:
    t = timeout if timeout is not None else _T_HEALTH
    try:
        with httpx.Client(timeout=t) as client:
            r = client.get(f"{BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def generate(prompt: str, system: str = "", model: str = "", timeout: float | None = None) -> str:
    t = timeout if timeout is not None else _T_GENERATE
    payload: dict = {
        "model": model or DEFAULT_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system
    with httpx.Client(timeout=t) as client:
        r = client.post(f"{BASE_URL}/api/generate", json=payload)
        r.raise_for_status()
        return r.json()["response"]


def generate_fast(prompt: str, system: str = "", timeout: float | None = None) -> str:
    """Use the fast model for lightweight ops: classify, outline, code_surface (non-Python)."""
    return generate(prompt=prompt, system=system, model=FAST_MODEL,
                    timeout=timeout if timeout is not None else _T_FAST)


def generate_tiny(prompt: str, system: str = "", timeout: float | None = None) -> str:
    """Use the tiny model for trivial ops: classify small inputs, outline, schema_infer."""
    return generate(prompt=prompt, system=system, model=TINY_MODEL,
                    timeout=timeout if timeout is not None else _T_TINY)


def generate_json(prompt: str, system: str = "", model: str = "", timeout: float | None = None) -> str:
    """Same as generate() but requests JSON-formatted output via Ollama format=json."""
    t = timeout if timeout is not None else _T_FAST
    payload: dict = {
        "model": model or FAST_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    if system:
        payload["system"] = system
    with httpx.Client(timeout=t) as client:
        r = client.post(f"{BASE_URL}/api/generate", json=payload)
        r.raise_for_status()
        return r.json()["response"]


def list_models() -> list[str]:
    """Return names of all locally available Ollama models."""
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{BASE_URL}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
