# impact-gate: small, standalone image for any CI with Docker.
#
# The measure is vendored, so the only runtime needs are Python, git (the tool
# scores git ranges via subprocess) and the two pip deps (lizard, PyYAML).
#
# Build:  docker build -t impact-gate .
# Score:  docker run --rm -v "$PWD:/repo" impact-gate score --mode range --base origin/main
FROM python:3.12-slim

# git is required at runtime: the gate reads staged/worktree/range diffs via git.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# CI mounts the repo owned by a different uid than the container user; without this
# git refuses to operate on it ("detected dubious ownership").
RUN git config --system --add safe.directory '*'

# Install the package from the build context, then drop the sources.
WORKDIR /src
COPY . /src
RUN pip install --no-cache-dir . \
    && rm -rf /src /root/.cache

# Run unprivileged. The repo to score is mounted at /repo.
RUN useradd --create-home --uid 1000 gate
USER gate
WORKDIR /repo

ENTRYPOINT ["impact-gate"]
CMD ["--help"]

LABEL org.opencontainers.image.title="impact-gate" \
      org.opencontainers.image.description="Measure and gate structural change-impact." \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/officefloor/ImpactGate"
