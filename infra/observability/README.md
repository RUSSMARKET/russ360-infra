# Russ360 — observability stack

Bootstrapped 2026-05-21 per [Phase 0 / Track A](../../docs/final-stage-cutover-cleanup-sprint-plan.md).
Status: [`/cutover-status/track-a-observability-infra.md`](../../cutover-status/track-a-observability-infra.md).

## Состав

| Контейнер | Образ | Хост-порт (loopback) | Tier | Назначение |
|---|---|---|---|---|
| `obs-prometheus` | `prom/prometheus:v2.55.1` | `9090` | metrics | TSDB + scrape |
| `obs-node-exporter` | `prom/node-exporter:v1.8.2` | `9100` (host net) | metrics | метрики хоста |
| `obs-cadvisor` | `gcr.io/cadvisor/cadvisor:v0.52.1` | — | metrics | per-container CPU/RAM |
| `obs-loki` | `grafana/loki:3.3.2` | `3100` | logs | log store (7d retention) |
| `obs-promtail` | `grafana/promtail:3.3.2` | — | logs | log shipper |
| `obs-grafana` | `grafana/grafana:11.4.0` | `3030` | ui | UI |
| `obs-glitchtip-postgres` | `postgres:16-alpine` | — | errors | DB |
| `obs-glitchtip-redis` | `redis:7-alpine` | — | errors | broker |
| `obs-glitchtip-migrate` | `glitchtip/glitchtip:v4.1` | — | errors | one-shot init |
| `obs-glitchtip-web` | `glitchtip/glitchtip:v4.1` | `8050` | errors | Sentry API/UI |
| `obs-glitchtip-worker` | `glitchtip/glitchtip:v4.1` | — | errors | celery + beat |

Все порты слушают только `127.0.0.1`. Наружу выпускаются через nginx vhost с basic auth (только на prod).

### Группировка контейнеров

Все контейнеры стека несут одинаковую метку и общий префикс — отсортировать в любом UI/CLI:

```bash
docker ps --filter label=stack=observability                                # все контейнеры стека
docker ps --filter label=stack=observability --filter label=tier=metrics    # только metrics tier
docker ps --filter name=^obs-                                                # по префиксу имени
```

Tier'ы: `metrics` (prometheus, node-exporter, cadvisor), `logs` (loki, promtail), `ui` (grafana), `errors` (glitchtip-*).

## Локально (smoke)

```bash
cd infra/observability
cp .env.example .env                                  # подставить пароли
mkdir -p /tmp/empty-prod /tmp/empty-dev               # placeholder bind-mounts
docker compose up -d
```

Проверить:

- Grafana: <http://localhost:3030> (admin / пароль из `.env`)
  - Dashboards → Russ360 → "Host overview" — метрики CPU/RAM/disk.
  - Explore → Loki → `{job="docker"}` — логи всех контейнеров стека.
- Prometheus: <http://localhost:9090/targets> — `prometheus`, `node_exporter`, `cadvisor` все UP.
- GlitchTip: <http://localhost:8050> — создать первого user'а через UI.

Тяжёлая остановка:

```bash
docker compose down -v   # ВНИМАНИЕ: -v стирает все volume'ы (TSDB, GlitchTip data)
```

## На сервере (prod)

Директория: `/root/russ360-infra/infra/observability/` (часть репы `RUSSMARKET/russ360-infra`, clone через deploy key `/root/.ssh/id_ed25519_russ360_infra`).

```bash
ssh shake
cd /root/russ360-infra
git pull
cd infra/observability
docker compose up -d
```

`.env` на сервере **не в репе** — лежит в `/root/russ360-infra/infra/observability/.env` (chmod 600). При первом clone скопировать из `/root/observability.env.bak.*` или сгенерить заново.

Перед запуском в `.env` выставить реальные пути логов rusaifin:

```env
RUSAIFIN_PROD_LOGS=/home/fintech/web/server.rusaifin.ru/public_html/storage/logs
RUSAIFIN_DEV_LOGS=/home/fintech/web/dev.server.rusaifin.ru/public_html/storage/logs
GLITCHTIP_DOMAIN=https://glitchtip.rusaifin.ru
GF_SERVER_ROOT_URL=https://observability.rusaifin.ru
GLITCHTIP_EMAIL_URL=smtp://localhost:25
OBS_HOSTNAME=prod
```

Поддомены создаются через Hestia (`v-add-web-domain`), затем proxy_pass на `127.0.0.1:3030` / `127.0.0.1:8050`. Поверх Grafana — basic auth в nginx.

## Структура

```
infra/observability/
├── compose.yml
├── .env.example
├── prometheus/
│   ├── prometheus.yml
│   └── alerts/                          # Track B
├── loki/loki-config.yml
├── promtail/promtail-config.yml
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/datasources.yml
│   │   ├── dashboards/dashboards.yml
│   │   └── alerting/                    # Track B (contact points, rules)
│   └── dashboards-json/
│       ├── host-overview.json
│       └── services-overview.json
└── glitchtip/                           # uploads volume root
```

## Известные локальные ограничения

- **cAdvisor + Docker 29 + containerd snapshotter (`io.containerd.snapshotter.v1`)** — per-container метрики (`container_memory_rss{name="..."}`) на локалке могут быть пустыми. Cadvisor ходит за `/var/lib/docker/image/overlayfs/layerdb/mounts/<id>/mount-id`, которого при containerd snapshotter нет. Хост-метрики (`id="/"`) работают; per-container проверять на prod (там docker storage driver другой).

## Track B (что появится позже)

- `/metrics` endpoints на 4 backend → раскомментировать scrape jobs в `prometheus/prometheus.yml`.
- Sentry SDK в сервисах → DSN из GlitchTip → exception tracking.
- Alert rules в `prometheus/alerts/*.yml` + Grafana contact points (Telegram).
- UptimeRobot пинг наружных URL.

## Whitelist принципы (важно)

Сервер shared с чужими проектами (`russ-market.ru` и др., см. memory `prod-server-shared`). Promtail фильтрует контейнеры по префиксам:

```
rusai* | fintech_* | glitchtip* | prometheus | loki | grafana | promtail | node_exporter | cadvisor
```

Чужое не индексируем.
