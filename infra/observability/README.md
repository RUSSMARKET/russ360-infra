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
docker compose -f compose.yml -f compose.scrape.yml up -d
```

> **Важно (Track B):** на сервере запускать с override `compose.scrape.yml` — он подключает
> `obs-prometheus` к `*_app-network` каждого backend, чтобы скрейпить `/metrics` по имени
> nginx-контейнера (хост-порты сервисов слушают только `127.0.0.1` и из bridge недоступны).
> Локально override НЕ применяется (этих сетей нет; app-скрейп локально не нужен).

`.env` на сервере **не в репе** — лежит в `/root/russ360-infra/infra/observability/.env` (chmod 600). При первом clone скопировать из `/root/observability.env.bak.*` или сгенерить заново.

Перед запуском в `.env` выставить реальные пути логов rusaifin:

```env
RUSAIFIN_PROD_LOGS=/home/fintech/web/server.rusaifin.ru/public_html/storage/logs
RUSAIFIN_DEV_LOGS=/home/fintech/web/dev.server.rusaifin.ru/public_html/storage/logs
GLITCHTIP_DOMAIN=https://glitchtip.rusaifin.ru
GF_SERVER_ROOT_URL=https://observability.rusaifin.ru
GLITCHTIP_EMAIL_URL=smtp://localhost:25
OBS_HOSTNAME=prod
# Telegram alerting (Track B) — bot token от @BotFather (секрет):
GF_TELEGRAM_BOT_TOKEN=123456:ABC...
```

> Chat id — **не секрет** и зашит в `grafana/provisioning/alerting/contactpoints.yaml`
> (`chatid: "..."`). Заменить плейсхолдер `"0"` на id целевого чата. Причина: Grafana
> мис-типизирует env-раскрытый числовой chat id в number и отклоняет (нужна строка) —
> поймано локальным smoke. Bot token (формат `digits:alnum`) остаётся строкой и идёт из env.

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
│       ├── services-overview.json
│       └── service-debug.json          # один сервис под лупой (templated + Loki)
└── glitchtip/                           # uploads volume root
```

## Известные локальные ограничения

- **cAdvisor + Docker 29 + containerd snapshotter (`io.containerd.snapshotter.v1`)** — per-container метрики (`container_memory_rss{name="..."}`) на локалке могут быть пустыми. Cadvisor ходит за `/var/lib/docker/image/overlayfs/layerdb/mounts/<id>/mount-id`, которого при containerd snapshotter нет. Хост-метрики (`id="/"`) работают; per-container проверять на prod (там docker storage driver другой).

## Track B (instrumentation)

Статус: [`/cutover-status/track-b-app-instrumentation.md`](../../cutover-status/track-b-app-instrumentation.md).

- **Scrape:** jobs `rusaicore` / `rusaiauth` / `rusaisklad` в `prometheus/prometheus.yml` (по имени nginx-контейнера через `compose.scrape.yml`). **`rusaifin` подключён 2026-06-11** — native php-fpm, скрейп по публичному vhost `https://server.rusaifin.ru:443/metrics` (и dev). `/metrics` закрыт IP-allowlist'ом `hestia/nginx.ssl.conf_metrics` (ставится в оба rusaifin-vhost'а; раньше был открыт в интернет). Все 11 таргетов UP.
- **Метрики приложений** (Prometheus namespace `russ360_`): `http_requests_total`, `http_request_duration_seconds`, `exceptions_total` (RED по всем сервисам) + бизнес: `active_sessions` (rusaifin), `active_tokens` (rusaiauth), `core_api_request_duration_seconds` / `core_gateway_errors_total` (sklad gateway).
  - ⚠ **rusaifin: env-метка ненадёжна для counter/histogram.** APCu расшарен на весь php8.3-fpm master (один master на версию PHP, юзер fintech), namespace `russ360` общий → `http_requests_total`/latency/exceptions у dev и prod **совпадают** (gauge `active_sessions` корректен — считается из своей БД). Отделить: `PROMETHEUS_STORAGE=redis` с разным DB-index по env. Не сделано.
- **Sentry SDK** в сервисах → DSN из GlitchTip → exception tracking (бэкенды `sentry/sentry-laravel`, фронты `@sentry/vue`).
- **Alerting** (provisioned): `grafana/provisioning/alerting/{rules,contactpoints,policies}.yaml`. Калибровка 2026-06-11 по 14д baseline:
  - метрики: `target-down (up==0)`, `5xx>1%`, `p95>2.5s` (окно 15m, гейт ≥3 req/min, SMS-роуты исключены), `exceptions>5/min`, `disk>80/95%`.
  - логи (Loki datasource, группа `russ360-logs`): `scheduler-fail` (Scheduled command + fail, >3 за 30m) и `critical-level` (>0 за 5m). Ловят то, что числовые метрики не видят.
  - контакт-поинт Telegram (`GF_TELEGRAM_BOT_TOKEN`, chat id в `contactpoints.yaml`).
- **Логи: единая схема меток.** promtail размечает все 4 backend меткой `{service,env}` (docker-сервисы — relabel из `compose_project`, rusaifin — из laravel job). LogQL-селектор `{service="...",env="..."}` работает одинаково для всех.
- **Dashboards:** `services-overview.json` (весь стек разом) + `service-debug.json` (uid `russ360-service-debug`: один сервис под лупой — dropdown service/env, RED, разбивка по роутам, логи с переходом в Explore).
- **CLI:** `scripts/russ obs {targets|query|logs|errors|alerts}` — read-only доступ к стеку из терминала (Prometheus/Loki/GlitchTip/Grafana).
- **UptimeRobot** пинг наружных URL — API платный на free-плане, не сделан. Кандидат на замену: self-hosted `blackbox-exporter`.

## Roadmap / backlog (отдельными заходами)

- **correlation-id (trace-id) сквозь сервисы** — пробросить один request-id заголовком (`X-Request-Id`) через rusaifin→rusaicore→rusaiauth→rusaisklad, писать его в каждую лог-строку (Monolog processor) и отдавать клиенту. Тогда по одному id виден полный путь распределённого запроса в Loki (`{...} |= "<id>"`). Стоимость: middleware + Monolog-processor в каждом из 4 сервисов + проброс в gateway-клиентах (`CoreApiClient` и аналоги). Высокая отдача для дебага распределённых багов; делать отдельным заходом, не точечно.
- **blackbox-exporter** — внешняя проверка доступности (TLS-срок, редиректы, реальный ответ) для Grafana/SSO/обоих фронтов; ловит то, что внутренний scrape не видит (упал nginx/протух сертификат).

## Whitelist принципы (важно)

Сервер shared с чужими проектами (`russ-market.ru` и др., см. memory `prod-server-shared`). Promtail фильтрует контейнеры по префиксам:

```
rusai* | fintech_* | glitchtip* | prometheus | loki | grafana | promtail | node_exporter | cadvisor
```

Чужое не индексируем.
