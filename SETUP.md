# Localthink MCP — Hardware Setup Guide

Pick your tier, run the two pull commands, set the two env vars. Done.

---

## Quick-reference table

| Tier | Hardware | `OLLAMA_MODEL` | `OLLAMA_FAST_MODEL` | Speed (tok/s) | Quality |
|------|----------|----------------|---------------------|---------------|---------|
| A | CPU only — 16 GB RAM | `qwen2.5:7b-instruct-q4_K_M` | `qwen2.5:1.5b` | 3-8 | ★★☆☆☆ |
| A+ | CPU only — 32 GB RAM | `qwen2.5:14b-instruct-q4_K_M` | `qwen2.5:3b` | 2-5 | ★★★☆☆ |
| B | 4 GB VRAM | `qwen2.5:7b-instruct-q4_K_M` | `qwen2.5:1.5b` | 20-40 | ★★☆☆☆ |
| C | 6 GB VRAM | `qwen2.5:7b-instruct-q6_K` | `qwen2.5:3b` | 25-45 | ★★★☆☆ |
| D | 8 GB VRAM | `qwen2.5:7b-instruct-q8_0` | `qwen2.5:3b` | 30-55 | ★★★★☆ |
| E | 10-12 GB VRAM | `qwen2.5:14b-instruct-q4_K_M` | `qwen2.5:3b` | 20-40 | ★★★★☆ |
| F | 16-20 GB VRAM | `qwen2.5:14b-instruct-q8_0` | `qwen2.5:7b-instruct-q4_K_M` | 20-35 | ★★★★★ |
| G | 24 GB VRAM | `qwen2.5:32b-instruct-q4_K_M` | `qwen2.5:7b-instruct-q4_K_M` | 15-30 | ★★★★★ |
| H | 48 GB+ VRAM | `qwen2.5:72b-instruct-q4_K_M` | `qwen2.5:14b-instruct-q4_K_M` | 8-18 | ★★★★★ |
| Apple M (8 GB) | M1/M2/M3 base | `qwen2.5:7b-instruct-q4_K_M` | `qwen2.5:1.5b` | 15-30 | ★★☆☆☆ |
| Apple M (16-24 GB) | M Pro / M1 Max | `qwen2.5:14b-instruct-q4_K_M` | `qwen2.5:3b` | 20-45 | ★★★★☆ |
| Apple M (32-40 GB) | M Max | `qwen2.5:32b-instruct-q4_K_M` | `qwen2.5:7b-instruct-q4_K_M` | 15-30 | ★★★★★ |
| Apple M (64-192 GB) | M Ultra | `qwen2.5:72b-instruct-q4_K_M` | `qwen2.5:14b-instruct-q4_K_M` | 10-25 | ★★★★★ |

> Speed is tokens/second for generation. Quality is relative — even ★★☆ is sufficient for summarisation and extraction.

---

## Prerequisites

### 1. Install Ollama

**Windows / macOS:**
Download from [ollama.ai](https://ollama.ai) and run the installer.

**Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

Verify:
```bash
ollama serve        # start the server (runs in background on Windows/macOS automatically)
curl http://localhost:11434/api/tags   # should return {"models":[...]}
```

### 2. GPU driver prerequisites

| GPU brand | What you need |
|-----------|--------------|
| NVIDIA | CUDA 11.8+ driver. Download from nvidia.com. Verify: `nvidia-smi` |
| AMD (Linux) | ROCm 5.7+. `sudo apt install rocm-hip-sdk`. Verify: `rocm-smi` |
| AMD (Windows) | Ollama uses DirectML automatically — no extra setup |
| Intel Arc | DirectML on Windows — automatic. Linux: limited, use CPU mode |
| Apple Silicon | Metal — automatic, nothing to install |
| CPU only | Nothing extra needed |

---

## Tier A — CPU only (16 GB RAM)

**Typical hardware:** Any laptop/desktop without a discrete GPU, or with an iGPU.

This tier is slow but functional. Use for batch overnight jobs, not interactive work.

```bash
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull qwen2.5:1.5b
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:7b-instruct-q4_K_M",
        "OLLAMA_FAST_MODEL": "qwen2.5:1.5b"
      }
    }
  }
}
```

**Tips:**
- Set `OLLAMA_NUM_PARALLEL=1` to avoid OOM if RAM is tight.
- Use `local_answer` and `local_extract` (targeted) rather than `local_summarize` (full pass) to minimise generation length.
- If 8 GB RAM: use `qwen2.5:3b` for both models instead. The 7B will likely cause swapping.

---

## Tier A+ — CPU only (32 GB RAM)

The 14B fits entirely in RAM. Noticeably better quality for complex summarisation.

```bash
ollama pull qwen2.5:14b-instruct-q4_K_M
ollama pull qwen2.5:3b
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:14b-instruct-q4_K_M",
        "OLLAMA_FAST_MODEL": "qwen2.5:3b"
      }
    }
  }
}
```

---

## Tier B — 4 GB VRAM

**Typical hardware:** GTX 1050 Ti, GTX 1650, RX 570/580, Intel Arc A380

The 7B Q4 model fits within 4 GB VRAM (needs ~4.7 GB peak — Ollama will offload a few layers to RAM if tight, which is fine with 16 GB+ system RAM).

```bash
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull qwen2.5:1.5b
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:7b-instruct-q4_K_M",
        "OLLAMA_FAST_MODEL": "qwen2.5:1.5b"
      }
    }
  }
}
```

**Tip:** If Ollama reports OOM, force the model smaller:
```bash
OLLAMA_MODEL=qwen2.5:3b-instruct claude
```

---

## Tier C — 6 GB VRAM

**Typical hardware:** GTX 1060 6GB, GTX 1660, RX 5600 XT, RTX 2060

The 7B fits comfortably. Step up to Q6_K quantisation for meaningfully better quality at the same model size.

```bash
ollama pull qwen2.5:7b-instruct-q6_K
ollama pull qwen2.5:3b
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:7b-instruct-q6_K",
        "OLLAMA_FAST_MODEL": "qwen2.5:3b"
      }
    }
  }
}
```

**Alternative fast model:** `phi3.5:3.8b` — Microsoft's Phi-3.5, exceptional reasoning for 3.8B parameters. Good if you run many classification/outline jobs.
```bash
ollama pull phi3.5:3.8b
```

---

## Tier D — 8 GB VRAM

**Typical hardware:** RTX 2070/2080, RTX 3070, RX 6700 XT, RX 6800, RTX 4060 Ti

Sweet spot: Q8_0 of the 7B is near-lossless quality and fits in 8 GB (~7.7 GB). This gives you the same model as larger tiers just without quantization degradation.

```bash
ollama pull qwen2.5:7b-instruct-q8_0
ollama pull qwen2.5:3b
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:7b-instruct-q8_0",
        "OLLAMA_FAST_MODEL": "qwen2.5:3b"
      }
    }
  }
}
```

**Alternative:** Want a bigger model at lower quality? `qwen2.5:14b-instruct-q3_K_M` (~6.5 GB) fits and gives 14B reasoning at Q3 quality. Better for complex summarisation, worse for code structure tasks.
```bash
ollama pull qwen2.5:14b-instruct-q3_K_M
```

---

## Tier E — 10-12 GB VRAM

**Typical hardware:** RTX 2080 Ti, RTX 3080 10GB, RTX 3080 12GB, RTX 4070, RX 6900 XT

The 14B Q4 fits (~9 GB). This is the first tier with a clear quality jump over the 7B for complex reasoning, multi-section summarisation, and code analysis.

```bash
ollama pull qwen2.5:14b-instruct-q4_K_M
ollama pull qwen2.5:3b
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:14b-instruct-q4_K_M",
        "OLLAMA_FAST_MODEL": "qwen2.5:3b"
      }
    }
  }
}
```

**Fast model upgrade:** With 12 GB to spare, you can afford a faster FAST model:
```bash
ollama pull qwen2.5:7b-instruct-q4_K_M   # use as FAST_MODEL for higher-quality classify/outline
```

---

## Tier F — 16-20 GB VRAM

**Typical hardware:** RTX 3090 (24GB but often paired, useful at 16 GB), RTX 4080, RTX 4080 Super, Tesla T4, Quadro RTX 5000

Use Q8_0 of the 14B (near-lossless, ~13.5 GB) or step up to 32B Q3 (~14 GB).

```bash
ollama pull qwen2.5:14b-instruct-q8_0
ollama pull qwen2.5:7b-instruct-q4_K_M
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:14b-instruct-q8_0",
        "OLLAMA_FAST_MODEL": "qwen2.5:7b-instruct-q4_K_M"
      }
    }
  }
}
```

**Alternative:** `qwen2.5:32b-instruct-q3_K_M` (~14 GB) — 32B model at Q3. Better for long-document summarisation, slightly worse for precise extraction than 14B Q8.

---

## Tier G — 24 GB VRAM

**Typical hardware:** RTX 3090, RTX 3090 Ti, RTX 4090, A5000, Titan RTX

The 32B Q4 fits comfortably (~19 GB). This is a significant quality jump for complex analysis, multi-document tasks, and code understanding.

```bash
ollama pull qwen2.5:32b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:32b-instruct-q4_K_M",
        "OLLAMA_FAST_MODEL": "qwen2.5:7b-instruct-q4_K_M"
      }
    }
  }
}
```

**Alternative fast model:** `qwen2.5:7b-instruct-q8_0` for near-lossless fast operations.

---

## Tier H — 48 GB+ VRAM

**Typical hardware:** Dual RTX 3090/4090 (NVLink), A100 40/80 GB, H100, L40, Quadro RTX 8000

The 72B Q4 fits (~43 GB). This delivers GPT-4-class performance locally. Recommended for deep code analysis, complex multi-document summarisation, and session compression of long technical conversations.

```bash
ollama pull qwen2.5:72b-instruct-q4_K_M
ollama pull qwen2.5:14b-instruct-q4_K_M
```

**Configuration:**
```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:72b-instruct-q4_K_M",
        "OLLAMA_FAST_MODEL": "qwen2.5:14b-instruct-q4_K_M"
      }
    }
  }
}
```

**For multi-GPU:** Ollama distributes layers across GPUs automatically. No extra config needed.

---

## Apple Silicon

Apple Silicon uses unified memory — the GPU and CPU share the same pool. This means "VRAM" is effectively your total RAM minus OS overhead (~3-4 GB for macOS). Ollama uses Metal automatically.

**Memory bandwidth** on Apple Silicon is exceptionally high (200-800 GB/s), making it significantly faster than similarly-sized GPU tiers for the same model. A 16 GB M2 Pro often outperforms a 12 GB discrete GPU at inference.

### M1 / M2 / M3 — 8 GB unified

Effective model memory: ~4.5 GB. Treat as Tier B.

```bash
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull qwen2.5:1.5b
```

### M1 Pro / M2 Pro / M3 Pro — 16-36 GB unified

16 GB: treat as Tier E. 32-36 GB: treat as Tier G.

```bash
# 16 GB:
ollama pull qwen2.5:14b-instruct-q4_K_M
ollama pull qwen2.5:3b

# 32-36 GB:
ollama pull qwen2.5:32b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M
```

### M1 Max / M2 Max / M3 Max — 32-96 GB unified

32-40 GB: treat as Tier G. 64-96 GB: between Tier G and H.

```bash
# 32-40 GB:
ollama pull qwen2.5:32b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M

# 64-96 GB:
ollama pull qwen2.5:72b-instruct-q4_K_M
ollama pull qwen2.5:14b-instruct-q4_K_M
```

### M2 Ultra / M3 Ultra — 128-192 GB unified

Full 72B with room to spare. One of the best local inference platforms available.

```bash
ollama pull qwen2.5:72b-instruct-q8_0    # near-lossless 72B
ollama pull qwen2.5:14b-instruct-q4_K_M
```

```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL": "qwen2.5:72b-instruct-q8_0",
        "OLLAMA_FAST_MODEL": "qwen2.5:14b-instruct-q4_K_M"
      }
    }
  }
}
```

---

## Quantization guide

| Quant | VRAM vs FP16 | Quality loss | Use when |
|-------|-------------|--------------|----------|
| `q2_K` | ~25% | High | Absolute minimum VRAM, acceptable for simple extraction |
| `q3_K_M` | ~35% | Moderate | Need a bigger model in limited VRAM |
| `q4_K_M` | ~50% | Low | **Default recommendation** — best balance |
| `q5_K_M` | ~60% | Very low | Extra headroom for quality without full FP16 cost |
| `q6_K` | ~75% | Minimal | When VRAM permits and quality matters |
| `q8_0` | ~80% | Negligible | Near-lossless; use when VRAM comfortably fits |
| FP16 (no quant) | 100% | None | Only if VRAM is abundant and you want absolute max |

**Rule of thumb:** `q4_K_M` is the right default. Step up one level (`q6_K` or `q8_0`) only when the model fits comfortably. Never go below `q4_K_M` for the DEFAULT model — quality degrades noticeably for complex summarisation.

---

## Full configuration reference

All settings can go in your MCP server config (Claude Code: `.claude/settings.json` under `mcpServers.localthink.env`):

| Env var | Default | Notes |
|---------|---------|-------|
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct-q4_K_M` | Used by all quality-sensitive tools |
| `OLLAMA_FAST_MODEL` | (same as OLLAMA_MODEL) | Used by classify, outline, symbols, translate, schema_infer, timeline |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Change if Ollama runs on another machine |

**Increase timeout for very large documents:**
The default is 120 s. For 32B+ models or documents > 50 KB add:
```json
{ "OLLAMA_TIMEOUT": "300" }
```
*(requires local source modification — not yet a built-in env var; workaround: pull a faster quantization)*

---

## Troubleshooting

**`[localthink] Ollama is not running`**
```bash
ollama serve
# or on macOS/Windows: check the system tray icon
```

**Model generates very slowly on GPU**
```bash
nvidia-smi   # check GPU utilization — should be 80-100% during inference
# If low: Ollama may be in CPU fallback mode
# Fix: ensure CUDA drivers are installed and up to date
```

**Out of memory / model fails to load**
```bash
# Option 1: use a smaller quantization
ollama pull qwen2.5:7b-instruct-q4_K_M   # instead of q8_0

# Option 2: reduce context size (Ollama default is 2048)
# Add to your Modelfile or use OLLAMA_NUM_CTX env var

# Option 3: close other GPU-heavy applications
```

**AMD GPU not detected on Windows**
Ollama uses DirectML on Windows for AMD. It should auto-detect. If not:
```powershell
# Check device in Device Manager → Display adapters
# Ensure Windows 10 2004+ / Windows 11
```

**Slow on Apple Silicon despite large unified memory**
```bash
# Ensure you're running the native ARM64 build of Ollama
file $(which ollama)   # should show: arm64
```

**`local_code_surface` on Python returns wrong output**
Python surface extraction uses the stdlib `ast` module with no Ollama involved. If results look wrong, the source file likely has a syntax error — check with:
```bash
python -m py_compile your_file.py
```
