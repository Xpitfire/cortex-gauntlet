# Track P sandbox base image: Node 22 + pnpm + Python + Playwright (chromium) + the probe.
# The candidate repo is layered on top at build time (see sandbox.py): it is COPYed in, installed,
# and built; a separate guarded `docker run` then installs a fail-closed firewall, drops privileges,
# serves the app, and runs the probe.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Node 22 from NodeSource. The Playwright *python* image ships no Node, and Jammy's apt `nodejs` is
# v12 — too old for corepack (which uses `??=`, a Node>=15 syntax), so the old line died at build.
# corepack ships with Node>=16.9, so enable it directly (no `npm i -g corepack`); pin pnpm for repro.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg iptables \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && corepack enable && corepack prepare pnpm@9 --activate \
    && rm -rf /var/lib/apt/lists/*

# This base ships the Playwright browsers (/ms-playwright) but not the Python packages used by the
# probe and sealed hidden-test runners. Pin every evaluator dependency so a cached image cannot change
# benchmark semantics underneath a run.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip3 install --no-cache-dir playwright==1.49.0 pytest==9.0.2 ruff==0.14.8

# non-root user for the serve/probe phase (uid 1000 == the Playwright image's pwuser). /work must be
# owned by 1000 so the candidate's `npm install`/build (run as 1000) can create node_modules there —
# COPY --chown sets the files but not the dir, so chown /work explicitly.
RUN useradd -m -u 1000 runner || true
RUN mkdir -p /work && chown 1000:1000 /work
WORKDIR /work

# the probe + egress-allowlist proxy are copied in by the build (standalone: stdlib + playwright only)
COPY probe.py /probe/probe.py
COPY egress_proxy.py /probe/egress_proxy.py
COPY network_guard.py /probe/network_guard.py

# candidate build args: the repo context is added by sandbox.py's generated Dockerfile stage.
# non-interactive corepack: a candidate whose package.json pins a pnpm version must not block on a prompt
ENV PORT=8080 HOST=127.0.0.1 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
USER 1000
