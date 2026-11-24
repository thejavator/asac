# The image a delegated step runs in: Claude Code, git and python3, no ASAC and no secrets.
#
#   docker build -t asac-agent:0.1.0 --build-arg ASAC_VERSION=0.1.0 docker/agent
#
# The runner starts it with no network, a read-only root, a non-root user and the run's worktree
# as the only writable mount (see DockerRunner.command). Nothing here holds a credential: the
# model API key is passed to the container by name at run time.
FROM node:22-slim

ARG CLAUDE_CODE_VERSION=2.1.331
ARG ASAC_VERSION=dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

# The runner starts the container as "nobody" with a read-only root and a tmpfs on /tmp, which is
# the only home the tool can write to. Its files stay out of the worktree: they are never committed.
# git is here for the agent's own use; the worktree's .git points at the main repository, which
# the container never sees, so ASAC makes the step's commit itself, outside the container.
ENV HOME=/tmp
LABEL org.opencontainers.image.title="asac-agent" \
      org.opencontainers.image.version="${ASAC_VERSION}" \
      dev.asac.claude-code="${CLAUDE_CODE_VERSION}"
WORKDIR /work
CMD ["sleep", "3600"]
