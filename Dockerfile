# One image for the CLI, the portal and the daemon. Project files are mounted at /project.
FROM python:3.13-slim AS build
RUN pip install --no-cache-dir uv
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv build --wheel --out-dir /dist

FROM python:3.13-slim
ARG OPA_VERSION=1.0.0
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL -o /usr/local/bin/opa \
       "https://github.com/open-policy-agent/opa/releases/download/v${OPA_VERSION}/opa_linux_$(dpkg --print-architecture | sed s/arm64/arm64_static/\;s/amd64/amd64_static/)" \
    && chmod 0755 /usr/local/bin/opa \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/*.whl)[postgres]" && rm /tmp/*.whl
RUN useradd --uid 10001 --create-home asac && mkdir -p /project /state && chown asac /state
USER 10001
WORKDIR /project
ENV ASAC_STATE_DIR=/state
EXPOSE 8080 8090
ENTRYPOINT ["asac"]
CMD ["portal", "--host", "0.0.0.0"]
