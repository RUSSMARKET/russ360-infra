# Track A — Observability infrastructure

**Status:** done (Track A scope) — следующий этап Track B
**Owner chat:** 2026-05-21..22 — bootstrap infra/observability/
**Last update:** 2026-05-22

## Done

- 2026-05-21: прочитан Phase 0 / Track A плана + ADR-0004 + infra_map; создан status-файл.
- 2026-05-21: разведка прод-сервера `shake` (порты, ресурсы, docker version, чужие проекты). Найдено: сервер shared (`russ-market.ru` и др.) — нужна фильтрация по нашим префиксам. Дисковый запас 43 GB → Loki retention урезан до 7d. План скорректирован, сохранён в memory (`prod-server-shared`, [[infra-map]]).
- 2026-05-21: создана структура `infra/observability/`:
  - `compose.yml` (10 контейнеров: prometheus, node_exporter, cadvisor, loki, promtail, grafana, glitchtip-{postgres,redis,migrate,web,worker})
  - provisioning: `grafana/provisioning/{datasources,dashboards}/*.yml`
  - dashboards JSON: `host-overview.json`, `services-overview.json` (placeholder для Track B)
  - конфиги: `prometheus/prometheus.yml`, `loki/loki-config.yml` (7d retention), `promtail/promtail-config.yml` (whitelist по префиксам `rusai*|fintech_*|glitchtip*|prometheus|loki|grafana|promtail|node_exporter|cadvisor`)
  - `README.md`, `.env.example`, `.gitignore`
- 2026-05-21: локальный smoke — стек поднят, всё зелёное:
  - Grafana http://localhost:3030 → 200, оба dashboards подхвачены через provisioning, обе datasources подключены
  - Prometheus http://localhost:9090/targets — `prometheus`, `node_exporter`, `cadvisor` все UP
  - Loki http://localhost:3100/ready → 200, Promtail шипит логи (`glitchtip-*`, `rusaifin_local-queue-1`) — фильтр работает
  - GlitchTip http://localhost:8050 → 200, миграции прошли, web+worker живы
- 2026-05-21: группировка контейнеров — префикс `obs-` ко всем + labels `stack=observability tier={metrics,logs,ui,errors}`. Видно в `docker ps --filter label=stack=observability` или `--filter name=^obs-`. Обновлены: compose.yml, promtail whitelist regex (`rusai|fintech_|obs-`), host-overview dashboard regex.
- 2026-05-21: **deploy на dev (shake) — зелёный**:
  - `/root/observability/` rsync из локалки, `.env` сгенерирован с random secrets (chmod 600)
  - все 10 контейнеров `Up` (cadvisor healthy), 3 prometheus targets UP
  - **cAdvisor per-container — работает на проде** (35 series с `name=` label) — overlay2 storage driver, в отличие от локалки с containerd snapshotter
  - Promtail видит наши логи: 4 backend сервиса × {dev, prod}, оба фронта, oba reverb, весь observability стек — 33 контейнера в whitelist. Чужого ничего нет
  - URL'ы пока только на `127.0.0.1` (наружу не выпускали — это в prod-фазе)
- 2026-05-22: **deploy на prod — публичные URL'ы live**:
  - A-записи в timeweb: `observability.rusaifin.ru` и `glitchtip.rusaifin.ru` → `82.146.57.149` (без AAAA, без привязки к виртуальному хостингу — timeweb gotcha обойдена)
  - Hestia кастомные templates `docker3030` (Grafana) и `docker8050` (GlitchTip) в `/usr/local/hestia/data/templates/web/{nginx,apache2}/`, склонированы из `docker8012` (rusaiauth)
  - **Грабли с LE**: исходный template имел `location ^~ /.well-known/acme-challenge/`, который перебивал Hestia's letsencrypt regex include (prefix `^~` > regex). Решение: убрать `location ^~` из template, добавить `include %home%/%user%/conf/web/%domain%/nginx.conf_letsencrypt*;` в HTTP-блок. Глобальный `error_page 404` редиректил наш 404 через `location /` → 301 → loop. После фикса LE прошёл с первой попытки.
  - vhosts под Hestia user `rusaifin` (как и `sso.*`); LE-сертификаты (Let's Encrypt R12) выданы и активны
  - GlitchTip vhost: `client_max_body_size 32m` (Sentry payloads)
  - `.env` обновлён: `GF_SERVER_ROOT_URL=https://observability.rusaifin.ru`, `GLITCHTIP_DOMAIN=https://glitchtip.rusaifin.ru`, `GLITCHTIP_EMAIL_URL=smtp://localhost:25`, `OBS_HOSTNAME=prod`
  - recreate: `obs-grafana`, `obs-glitchtip-{web,worker}`, `obs-promtail` — все Up
  - External smoke зелёный:
    - `https://observability.rusaifin.ru/api/health` → 200, database OK
    - `https://glitchtip.rusaifin.ru/api/0/` → 200
    - HTTP→HTTPS 301 redirect
    - Grafana `root_url` self-report: `https://observability.rusaifin.ru`

## In progress

- —

## Blocked

- —

## Next

- Track B kickoff: scrape jobs (закомментированы в `prometheus/prometheus.yml`) расскоментируются после инструментации сервисов.
- **Baseline неделя (Phase 0 sync point)**: смотреть dashboards, калибровать что считать «нормой», искать false-positive alerts. Не активировать alert rules до Track B.

## Known issues

- **cAdvisor + Docker 29 + containerd snapshotter** на локалке не enriched per-container метрики (`name=` label пустой). Хост-метрики работают. На проде — overlay2 storage driver, всё OK. Записано в `infra/observability/README.md`.

## Открытые TODO (вне Track A scope)

- Basic auth поверх Grafana login (defense-in-depth) — не делалось в этой фазе; если нужно, добавить через per-domain include в Hestia vhost.
- GlitchTip user registration: сейчас открыт (default). Когда создашь свой first user — добавить `ENABLE_USER_REGISTRATION=False` в `.env` и recreate `obs-glitchtip-web`.
- Telegram bot, UptimeRobot — Track B.

## Artifacts

- `infra/observability/` — структура и конфиги (этой сессии)
- `cutover-status/track-a-observability-infra.md` (этот файл)
- `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 0, Track A — спека)
- `docs/adr/0004-what-we-do-not-do.md` (триггер observability сработал 2026-05-21)
- memory: `prod-server-shared.md` (новая), `infra-map.md` (updated)
