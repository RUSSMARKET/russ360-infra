FROM golang:1.18 AS builder

ARG MIGRATOR_COMMIT=4cad6353cd3bc0056c50b1c407218dcba3bae445
WORKDIR /src
RUN git clone https://github.com/rl0nergan/grafana-db-migrator.git . \
    && git checkout --detach "${MIGRATOR_COMMIT}"
COPY preserve-logql-backticks.patch /tmp/preserve-logql-backticks.patch
RUN git apply /tmp/preserve-logql-backticks.patch
COPY sanitize_test.go pkg/sqlite/sanitize_test.go
RUN go test ./pkg/sqlite && make

FROM debian:bullseye-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates sqlite3 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/dist/grafana-db-migrator /usr/local/bin/grafana-migrate
ENTRYPOINT ["/usr/local/bin/grafana-migrate"]
