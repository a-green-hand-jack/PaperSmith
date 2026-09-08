# harbor-canary GUID {{canary}}
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    TEXINPUTS=/workspace/texmf//: \
    BSTINPUTS=/workspace/texmf//:

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip procps \
        texlive-full \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY texmf/ /workspace/texmf/
COPY materials/ /workspace/materials/

RUN mkdir -p /workspace/submission
CMD ["/bin/sh"]
