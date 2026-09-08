# harbor-canary GUID {{canary}}
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    TEXINPUTS=/tests/texmf//: \
    BSTINPUTS=/tests/texmf//:

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        texlive-full \
        python3 \
        python3-pip \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --break-system-packages --no-cache-dir \
    pytest==9.1.1 pytest-json-ctrf==0.5.2

# Separate-mode verifiers skip the tests/ upload, so the image must own
# /tests/* itself. Build context is this directory (tests/).
COPY . /tests/

# Artifacts declared in task.toml land here.
RUN mkdir -p /workspace/submission
