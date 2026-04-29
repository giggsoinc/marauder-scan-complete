# =============================================================
# FILE: Dockerfile
# VERSION: 1.2.0
# UPDATED: 2026-04-29
# OWNER: Giggso Inc
# PURPOSE: PatronAI scanner + Streamlit container.
#          Python 3.12 slim base. Minimal attack surface.
#          Runs main.py which starts scanner threads + Streamlit.
#          Bundles Marauder Scan code layer (llama.cpp + Gemma 4 E4B).
# PORT: 8501 (Streamlit settings UI)
# =============================================================

FROM python:3.12-slim

# Metadata
LABEL maintainer="Giggso Inc" \
      version="1.0.0" \
      description="PatronAI — Giggso Inc"

# Prevents Python from writing .pyc files and buffers stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# System dependencies
# genisoimage — creates HFS disk images (macOS DMG) on Linux
# nsis        — Nullsoft Scriptable Install System, creates Windows EXE installers on Linux
# weasyprint GTK/GLib deps — Debian 12 Bookworm renamed libglib2.0-0 → libglib2.0-0t64
#   libgobject-2.0.so.0 is inside libglib2.0-0t64; without it weasyprint
#   raises OSError on import and the Reports page crashes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    genisoimage \
    nsis \
    libglib2.0-0t64 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libharfbuzz0b \
    fonts-dejavu-core \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/       ./src/
COPY dashboard/ ./dashboard/
COPY config/    ./config/
COPY scripts/   ./scripts/
COPY agent/     ./agent/
COPY assets/    ./assets/
COPY docs/      ./docs/
COPY main.py    .

# Streamlit config — dark theme + server settings (from .streamlit/config.toml)
RUN mkdir -p /root/.streamlit
COPY .streamlit/config.toml /root/.streamlit/config.toml

# Non-root user for security
RUN useradd -m -u 1000 scanner \
    && chown -R scanner:scanner /app /root/.streamlit
USER scanner

EXPOSE 8501

# ── Marauder Scan — llama.cpp + Qwen 3 1.7B classifier ───────
# Build llama.cpp binary used to run the AMBIGUOUS-snippet classifier.
# Pinned to a release tag rather than HEAD for deterministic builds.
# To bump: confirm the new tag still supports Qwen 3 architecture, then update
# LLAMA_CPP_TAG. Qwen 3 architecture support landed in b5000; do not use b4939 or earlier.
USER root
ARG LLAMA_CPP_TAG=b8960
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libcurl4-openssl-dev git \
    && git clone --depth 1 --branch "${LLAMA_CPP_TAG}" \
       https://github.com/ggml-org/llama.cpp /tmp/llama.cpp \
    && cmake /tmp/llama.cpp -B /tmp/llama.cpp/build \
       -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF \
    && cmake --build /tmp/llama.cpp/build --config Release -j4 \
       --target llama-cli --target llama-server \
    && cp /tmp/llama.cpp/build/bin/llama-cli /usr/local/bin/ \
    && cp /tmp/llama.cpp/build/bin/llama-server /usr/local/bin/ \
    && mkdir -p /etc/llama \
    && cp /tmp/llama.cpp/grammars/json.gbnf /etc/llama/ \
    && rm -rf /tmp/llama.cpp \
    && apt-get remove -y build-essential cmake git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Qwen 3 1.7B classifier — bake when INCLUDE_CLASSIFIER=1 (adds ~1 GB).
# Default: skip the bake. Three runtime options when skipped:
#   1. Mount the GGUF at /models from the EC2 host (-v /opt/patronai/models:/models).
#   2. Provide CODE_ANALYSER_MODEL=s3://… and download on first start.
#   3. Do nothing — code_fallback.regex_fallback() classifies AMBIGUOUS hits.
# With the regex fallback present, the system stays fully functional whether or
# not the classifier is reachable — it simply increases classification fidelity.
# Why Qwen 3 1.7B: Apache 2.0, native function-calling, ~3× smaller than Gemma 4 E4B,
# stronger JSON-mode reliability. Verify the official Qwen GGUF repo at build time;
# if missing, replace QWEN_GGUF_REPO with a community quantizer
# (e.g. bartowski/Qwen3-1.7B-GGUF) and rebuild.
ARG INCLUDE_CLASSIFIER=0
ARG QWEN_GGUF_REPO=Qwen/Qwen3-1.7B-GGUF
RUN mkdir -p /models && \
    if [ "$INCLUDE_CLASSIFIER" = "1" ]; then \
        llama-cli -hf "${QWEN_GGUF_REPO}:Q4_K_M" \
            --n-predict 1 --log-disable && \
        cp /root/.cache/llama.cpp/Qwen3-1.7B*.gguf /models/qwen3-1.7b-q4_k_m.gguf; \
    fi

RUN chown -R scanner:scanner /usr/local/bin/llama-cli /usr/local/bin/llama-server /etc/llama /models 2>/dev/null || true
USER scanner

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["python", "main.py"]
