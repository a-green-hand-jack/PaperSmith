FROM node:22-bookworm-slim AS builder
ARG AGENT_NAME=papersmith
ARG PI_VERSION=latest
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git python3 python3-venv python3-pip && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --break-system-packages --no-cache-dir uv
WORKDIR /opt/agent
COPY src /opt/agent/src
COPY distribution /opt/agent/distribution
RUN AGENT_NAME=$AGENT_NAME PREFIX=/opt/install SKIP_RUNTIME_INSTALL=1 PI_VERSION=$PI_VERSION /opt/agent/distribution/install.sh

FROM node:22-bookworm-slim AS runtime
ARG AGENT_NAME=papersmith
ARG PI_VERSION=latest
ARG PI_PACKAGE=@earendil-works/pi-coding-agent
ARG BOHR_VERSION=2.6.74
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates python3 \
    texlive-full \
  && rm -rf /var/lib/apt/lists/*
# pi is the only coding-agent backend. bohr-cli is a domain tool (Bohrium LKM
# depth enrichment and PDF text), not a backend.
RUN npm install --global \
  ${PI_PACKAGE}@${PI_VERSION} \
  @dptech-corp/bohr-cli@${BOHR_VERSION} \
  --ignore-scripts --no-audit --no-fund
# Refreshing the catalog is not what makes models appear: `pi --list-models` is
# auth-filtered, so "No models available" in a keyless image is a credential
# condition, not a missing catalog.
RUN pi update --models || echo 'warning: model catalog refresh failed'
COPY --from=builder /opt/install /opt/install
COPY --from=builder /opt/agent/distribution/container-entrypoint.sh /usr/local/bin/agent-entrypoint
RUN chmod +x /usr/local/bin/agent-entrypoint && mkdir -p /root/.pi/agent /run/secrets
RUN mkdir -p /workspace
WORKDIR /workspace
ENV AGENT_NAME=$AGENT_NAME
ENV PATH="/opt/install/lib/${AGENT_NAME}/environment/bin:/opt/install/bin:$PATH"
ENTRYPOINT ["/usr/local/bin/agent-entrypoint"]
