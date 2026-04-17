"""Multi-pass refinement: draft (fast) → refine (main) → verify (fast).

passes=1  Current single-call behaviour — no change.
passes=2  Fast draft, then main-model refine against the original request.
passes=3  + a fast verify step; if gaps are found, one final main refine.

All imports from ollama_client / prompts are deferred so this module loads
correctly regardless of sys.path setup order in server.py.
"""
from __future__ import annotations


def run_passes(
    prompt: str,
    system: str,
    passes: int = 1,
    timeout: float | None = None,
) -> str:
    """Run 1–3 LLM passes over `prompt` using `system`. Returns final output string.

    timeout=None defers to LOCALTHINK_TIMEOUT / LOCALTHINK_FAST_TIMEOUT env vars
    (set via local_config). Pass an explicit float to override."""
    if passes <= 1:
        from ollama_client import generate
        return generate(prompt=prompt, system=system, timeout=timeout)

    from ollama_client import generate, generate_fast
    from prompts import REFINE_SYSTEM, VERIFY_SYSTEM

    # Pass 1 — fast draft (uses LOCALTHINK_FAST_TIMEOUT when timeout=None)
    draft = generate_fast(prompt=prompt, system=system, timeout=timeout)

    # Pass 2 — main model refine (uses LOCALTHINK_TIMEOUT when timeout=None)
    refine_prompt = (
        f"Original request:\n{prompt}\n\n"
        f"Draft output to improve:\n{draft}"
    )
    draft = generate(prompt=refine_prompt, system=REFINE_SYSTEM, timeout=timeout)

    if passes >= 3:
        # Pass 3 — fast verify
        verify_prompt = (
            f"Original request:\n{prompt}\n\n"
            f"Response to check:\n{draft}"
        )
        verdict = generate_fast(
            prompt=verify_prompt, system=VERIFY_SYSTEM, timeout=timeout
        )
        if "PASS" not in verdict.upper()[:80]:
            # Gaps found — one more main refine incorporating reviewer feedback
            refine2_prompt = (
                f"Original request:\n{prompt}\n\n"
                f"Current draft:\n{draft}\n\n"
                f"Reviewer gaps to address:\n{verdict}"
            )
            draft = generate(
                prompt=refine2_prompt, system=REFINE_SYSTEM, timeout=timeout
            )

    return draft
