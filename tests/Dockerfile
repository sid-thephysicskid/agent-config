# A machine with no ~/.claude, no installed guard, and a pinned Python.
#
# The point is not portability, it is that a rule whose verdict depends on the
# developer's host fails here rather than passing by accident. It also proves
# the Python floor the README states, which the GitHub runners cannot: 3.9 is
# the oldest they offer.
#
#   docker build -f tests/Dockerfile --build-arg PYTHON=3.8 -t agent-config:3.8 .
#   docker run --rm agent-config:3.8
ARG PYTHON=3.13
FROM python:${PYTHON}-slim
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY . .
RUN useradd -m runner && chown -R runner /repo
USER runner
CMD ["bash", "scripts/sandbox"]
