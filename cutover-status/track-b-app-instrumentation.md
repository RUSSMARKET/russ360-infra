# Track B — Application instrumentation

**Status:** in progress
**Owner chat:** dolgan / 2026-05-25 session
**Last update:** 2026-05-25
**Depends on:** Track A (done) — observability stack live on prod.

> ⚠️ **НЕ cutover-specific.** Track B идёт обычным flow: feature branch → dev → main → prod.
> **НЕ работать на `cutover-final`.** Все репо инструментируются на ветке `feature/track-b-instrumentation`.

## Зафиксированные решения (конвенции)

### 1. Sentry / GlitchTip DSN
- 1 GlitchTip-проект на сервис (6): `rusaiauth`, `rusaicore`, `rusaifin`, `rusaisklad-back`, `fintech-front`, `rusaisklad-front`.
- PHP: `SENTRY_LARAVEL_DSN` в `.env` (gitignored), `SENTRY_ENVIRONMENT=${APP_ENV}`, `SENTRY_TRACES_SAMPLE_RATE=0.1`.
- Front: `NUXT_PUBLIC_SENTRY_DSN` через runtimeConfig.
- DSN пустой локально → Sentry — no-op. Проекты + DSN создаются в deploy-фазе (GlitchTip UI/API на prod).
- После первого GlitchTip-юзера → `ENABLE_USER_REGISTRATION=False` + recreate `obs-glitchtip-web` (закрываем Track A TODO).

### 2. `/metrics` — IP-allowlist на nginx (без basic auth)
- Endpoint в корне (`/metrics`, не под `/api`). Скрейпится obs-prometheus через host-published nginx-порт.
- nginx `location = /metrics`: allow loopback + `10/8`, `172.16/12`, `192.168/16`; `deny all`.
- В Laravel route публичный (без `auth:oauth`), защита — только на nginx.

### 3. Metrics-библиотека — `promphp/prometheus_client_php` + самописный тонкий слой
- Выбор «самописный» (kickoff допускал spatie или самописный). Причина: полный контроль над именами `russ360_*` и лейблами, меньше магии (дух ADR-0004).
- Компоненты (копируются 1:1 между backend): `App\Infrastructure\Observability\MetricsRegistry`, `App\Http\Middleware\PrometheusRequestMetrics`, `App\Http\Controllers\MetricsController`, `App\Providers\ObservabilityServiceProvider`, `config/prometheus.php`.
- **Storage = APCu** (`PROMETHEUS_STORAGE=apcu`) — php-fpm pool shared memory, без Redis-зависимости. ext-apcu добавлен в Dockerfile. Тесты — `inmemory` (phpunit.xml). Redis-адаптер доступен опцией.
- **Service/env лейблы НЕ эмитятся приложением** — их вешает Prometheus на scrape target (избегаем `exported_service` clash).

### 4. Имена метрик
- `russ360_http_requests_total{method,route,status}` (counter)
- `russ360_http_request_duration_seconds{method,route}` (histogram; buckets 0.025..10s)
- `russ360_exceptions_total` (counter) — из `report()` callback в bootstrap/app.php; даёт «error rate» в Prometheus вместо опроса GlitchTip → единый алертинг.
- route-лейбл = matched route pattern (`v1/projects/{id}`), не raw path → нет cardinality-взрыва.
- Бизнес-метрики по сервисам (план): rusaicore — RED+exceptions (он сам Core API → его histogram = «Core API latency»); rusaiauth — active_sessions (tokens); rusaifin/sklad — active_sessions (online_in), core_api_*, core_gateway_errors, dualwrite_fallback.

### 5. JSON-логи
- Контейнерные (auth/core/sklad): env-флип `LOG_CHANNEL=stderr` + `LOG_STDERR_FORMATTER=Monolog\Formatter\JsonFormatter` (канал `stderr` уже есть → кода не требует). Применяется на dev/prod через `.env`.
- rusaifin (native, не docker): нужен json file-канал → `storage/logs/laravel.log` + Promtail host-path JSON stage.

## Прогресс по сервисам

Все backend — на ветке `feature/track-b-instrumentation` (от origin/dev). Push на «иди на dev».

| Сервис | Sentry | /metrics | Бизнес-метрика | JSON-логи | Тесты |
|---|---|---|---|---|---|
| rusaicore | ✅ | ✅ | — (он сам Core API) | env stderr | ✅ 66 green |
| rusaiauth | ✅ | ✅ | active_tokens | env stderr | ✅ obs green (suite: 1 pre-existing RecoveryFlow fail) |
| rusaisklad_back | ✅ | ✅ | core_api latency + core_gateway_errors | env stderr | ✅ obs 6 green |
| rusaifin | ✅ | ✅ | active_sessions | `json` channel (LOG_CHANNEL=json) | ✅ obs 4 green |
| fintech (front) | — | n/a | n/a | n/a | — |
| rusaisklad_front | — | n/a | n/a | n/a | — |

### Деплой-нюансы по сервисам
- **APCu** добавлен в Dockerfile всех 4 backend (rusaicore cli+fpm, rusaiauth cli+fpm, sklad php_base, rusaifin local). **rusaifin prod — native php-fpm, НЕ docker** → apcu нужно поставить на хосте (`pecl install apcu` + ini), иначе storage сам деградирует в in-memory (метрики не агрегируются между воркерами, но app не падает).
- **JSON-логи:** контейнерные сервисы — env `LOG_CHANNEL=stderr` + `LOG_STDERR_FORMATTER=Monolog\Formatter\JsonFormatter` (канал уже есть). rusaifin prod (native) — `LOG_CHANNEL=json` (новый канал → laravel.log, Promtail host-path).
- **nginx allowlist `/metrics`:** добавлен в docker nginx-конфиги (auth/core/sklad/rusaifin-local). **rusaifin prod (Hestia native nginx)** — allowlist добавить через per-domain include (как в [[observability_stack]] про кастомные templates), не из репы.

## Done

- **2026-05-25 — план утверждён** (per-service + DSN/endpoint конвенция + alert rules yaml). Решение по metrics-либе пересмотрено: spatie → самописный promphp (см. выше).
- **2026-05-25 — rusaicore инструментирован** (commit `10508b5` на `feature/track-b-instrumentation`).
  - Sentry SDK ^4.25, promphp ^2.15. /metrics root-route + RED middleware на api-группе. exceptions counter из report(). APCu в обоих Dockerfile (cli + fpm-alpine). nginx allowlist. unit+feature тесты, полный suite 66 green. Локальный smoke: APCu-агрегация подтверждена (counter/histogram растут между запросами, /metrics себя не считает).

## DEV DEPLOY — в процессе (2026-05-25)

**Готово на dev (shake), верифицировано:**
- **obs-стек:** `git pull` russ360-infra + `compose.scrape.yml` (obs-prometheus в 6 app-networks) + bot token в `.env`. Grafana healthy, 5 alert rules + Telegram contact + дашборд. **Telegram доставка подтверждена** (тест-сообщение в группу «RSM Infra»).
- **GlitchTip:** 6 проектов + DSN (ids 1-6). DSN вписаны в `.env` сервисов на shake (не в git).
- **rusaicore dev:** UP — apcu, метрики в Prometheus (`russ360_http_requests_total{...}`), LOG_CHANNEL=stderr JSON, GlitchTip события (manual+SDK).
- **rusaiauth dev:** UP — потребовался host `composer install` (auth-app bind-маунтит весь чекаут `./:/var/www/html` → vendor с хоста, не из образа).
- **rusaisklad_back dev:** UP — apcu, config ок, target UP (app использует vendor из образа, как rusaicore).

**Баги, пойманные и пофикшенные при dev-деплое (закоммичены в dev):**
1. `apcu_enabled()` fallback — apcu выключен в CLI (`apc.enable_cli=0`) → artisan/queue крашились на APC::__construct при resolve MetricsRegistry. Фикс во всех 4 backend.
2. rusaiauth `.dockerignore` не исключал `vendor` → `COPY . .` затирал свежий vendor (с sentry) стейлом → package:discover «Integration not found». Добавлен `vendor`.
3. Grafana boot-safe: пустой Telegram bot token → крашлуп; numeric chatid через env → reject. Bot token из env с placeholder-дефолтом, chatid захардкожен.

**Ключевые различия dev-compose (важно для prod):**
- rusaicore / rusaisklad_back `app`: vendor **из образа** (бинд только .env/storage/cache) → деплой = build+recreate.
- rusaiauth `auth-app`: бинд-маунт **всего чекаута** → нужен `composer install` на хосте (vendor с хоста). ⚠️ Проверить, так ли на prod-compose каждого сервиса перед prod-деплоем.

**Осталось на dev (требует внимания/решений — НЕ доделано):**

- **rusaifin dev — НЕ ТРОНУТ (риск).** Чекаут `/home/fintech/web/dev.server.rusaifin.ru/public_html` на ветке `dev`, но **0 behind / 11 ahead** origin/dev — 11 НЕотправленных коммитов (вероятно параллельный чат). vhost `dev.server.rusaifin.ru/nginx.conf` → `proxy_pass http://82.146.57.149:8080` (механизм подачи неясен — не нашёл php-fpm пул `dev.server.rusaifin.ru` на php8.3; только prod-домены). Перед деплоем: (1) выяснить, что слушает :8080 и где vendor рантайма; (2) решить судьбу 11 коммитов. Мой obs-код в origin/dev (58d9d68) — ancestor, т.е. в чекауте присутствует. Scrape rusaifin всё равно отложен (native, нет app-network).
- **fintech front dev — ✅ DONE.** `.env` + DSN id5, `npm ci` + `npm run generate`. DSN запечён в `.output/public/_nuxt/*.js` (DSN_BAKED), фронт отдаёт 200. Грабля: пришлось снести root-owned `node_modules`/`.nuxt`/`.output` (memory fintech-front-gotcha #3) и переустановить от fintech.
- **rusaisklad_front dev — код готов, деплой ЗАБЛОКИРОВАН.** Pushed: `@sentry/vue` plugin + `Dockerfile.front.{dev,prod}` build-ARG для DSN + `compose.front.{dev,prod}.yml` `build.args` (DSN из shell-env, не в git). На shake `git pull` блокируется: (1) remote = кастомный SSH-алиас `git@github-rusaisklad-front:...`, резолвится только под спец deploy-юзером (не HOME Rusaisklad); (2) root-owned `local-bibli/package.json` (артефакт). **Решение:** деплоить через `deploy/deploy.sh` с `NUXT_PUBLIC_SENTRY_DSN=<id6> NUXT_PUBLIC_SENTRY_ENVIRONMENT=dev` в env (compose `build.args` подхватит) — он сам разрулит bibli/SSH. Чекаут оставлен в исходном состоянии (ничего не сломано). Build: `NUXT_PUBLIC_SENTRY_DSN=... docker compose -p rusaisklad_front_dev -f compose.front.dev.yml build && up -d --force-recreate`.

**Prod-деплой:** ждёт явного «иди на прод». Учесть: per-service bind-mount стратегию (host composer где нужно), rusaifin native (apcu на host prod, Hestia nginx /metrics allowlist, scrape-vhost), DSN с SENTRY_ENVIRONMENT=production.

## In progress

- Deploy-фаза (gated). Решения пользователя 2026-05-25:
  - **Деплой:** ждать завершения D4 (rusaicore/rusaifin checkout'ы были frozen под параллельный D4-чат). Память показывает D4 done (`track_d4_writer_switch_done`) — ждём явного «D4 закончен» / «иди на dev».
  - **GlitchTip DSN:** создаю сам через API.
  - **Telegram:** пользователь пришлёт bot token + chat id.

## Deploy-фаза — разведка и план (2026-05-25)

### GlitchTip — проекты СОЗДАНЫ (2026-05-25, prod)
- org `russmarket` (id=1), team `russ360`, 6 проектов (idempotent get_or_create):
  `rusaicore`(id1), `rusaiauth`(id2), `rusaifin`(id3), `rusaisklad-back`(id4), `fintech-front`(id5), `rusaisklad-front`(id6).
- DSN получены (`ProjectKey.get_dsn()` → `https://<key>@glitchtip.rusaifin.ru/<id>`). **В git НЕ коммичу** (ingestion-ключи, полу-секрет). На деплое впишу в `.env` каждого сервиса; источник истины — GlitchTip (перечитать idempotent-скриптом через `obs-glitchtip-web ./manage.py shell`).
- Регистрация уже закрыта (`enableUserRegistration:false`) — Track A TODO выполнен ранее, доп.действий не нужно.

### UptimeRobot — только ручное создание (free plan)
- Аккаунт заведён, Main API key есть. Но **free plan запрещает создание мониторов через API** (`newMonitor` → `access_denied: not allowed with your current plan`; read-методы работают). Telegram-контакт тоже за платным тарифом → используем **email** (контакт id 8457318, `dolgantraff@…`, активен).
- **Заводить мониторы вручную в UI** (4 шт., HTTP(s), 5 мин, alert contact = email):
  - `russ360 · Grafana` → `https://observability.rusaifin.ru/api/health`
  - `russ360 · SSO` → `https://sso.rusaifin.ru/.well-known/openid-configuration`
  - `russ360 · fintech front` → `https://fintech.rusaifin.ru/`
  - `russ360 · sklad front` → `https://rusaisklad.ru/`
- Все 4 URL проверены: отдают 200. Keyword-мониторинг — опционально позже в UI.

### Telegram — chat id определён
- Бот добавлен в группу **«RSM Infra»**, chat id **`-5136374164`** → вписан в `contactpoints.yaml` (`chatid`, не секрет, закоммичен).
- Bot token — держу для серверного `.env` (`GF_TELEGRAM_BOT_TOKEN`), в git/memory не пишу.

### GlitchTip (prod glitchtip.rusaifin.ru) — состояние (история разведки)
- API v4.1.5, `/api/0/` → 200.
- **`enableUserRegistration: false`** — регистрация уже закрыта (Track A TODO «закрыть после first user» — выполнено кем-то).
- Read-only counts: **users=1, orgs=1, projects=0**. First-user + org уже есть.
- Следствие: чисто-API создание 6 проектов требует **auth-токен** существующего юзера (креды не читаю) ИЛИ создание через `obs-glitchtip-web ./manage.py` (прод-write, нужен «иди на прод»).
- План: создать 6 проектов (`rusaicore`, `rusaiauth`, `rusaifin`, `rusaisklad-back`, `fintech-front`, `rusaisklad-front`) в существующей org → забрать DSN из project keys → прописать в `.env` каждого сервиса (gitignored, в файлы/memory не коммичу).

### Scrape networking — решено (см. infra commit)
- obs-prometheus (bridge) НЕ достаёт `127.0.0.1:80XX` сервисов. Подтверждено на shake (connection refused через 172.17.0.1).
- Решение: `compose.scrape.yml` (server-only override) подключает obs-prometheus к 6 `*_app-network`; scrape по имени nginx-контейнера:80. Локально override не применяется.

### Telegram — провижининг провалидирован локальным smoke (важная грабля)
- **Грабля:** Grafana крашлупит, если (а) Telegram bot token ПУСТОЙ (`could not find Bot Token`), или (б) chat id приходит через env-expansion как число (`cannot unmarshal number into ... chatid of type string`) — Grafana re-типизирует раскрытое числовое значение.
- **Решение (провалидировано):**
  - `bottoken: "${GF_TELEGRAM_BOT_TOKEN}"` — секрет из env; формат `digits:alnum` остаётся строкой. Непустой placeholder-дефолт в compose (`0000000000:PLACEHOLDER...`) → Grafana всегда стартует; реальный токен из `.env`.
  - `chatid: "0"` — **захардкожен** в contactpoints.yaml (не секрет). Заменить `"0"` на реальный chat id когда пользователь пришлёт. `GF_TELEGRAM_CHAT_ID` из compose убран.
- **Локальный smoke зелёный:** Grafana health=200, заприсижено 5 alert rules + Telegram contact point + дашборд `Services overview`. (До фикса Grafana крашлупила — поймано до прода.)

## Next

- fintech → rusaisklad_front (@sentry/nuxt).
- Infra wiring: расскоментировать scrape jobs (prometheus.yml), alerting provisioning, README.
- Deploy-фаза: GlitchTip проекты+DSN, Telegram bot, UptimeRobot.

## Done (продолжение)

- **2026-05-25 — rusaiauth** (commits на feature branch): Sentry + /metrics + active_tokens + terminate-middleware + apcu-fallback. obs-тесты гоняются в контейнере (host без pdo_sqlite). 1 pre-existing fail в `RecoveryFlowTest` подтверждён на чистом origin/dev — не наш.
- **2026-05-25 — rusaisklad_back**: Sentry + /metrics + CoreApiClient инструментирован (core_api latency / core_gateway_errors). Чужой doc-реорг WIP (53 del + 3 new docs) изолирован в **stash@{0}** на ветке — отдать автору.
- **2026-05-25 — rusaicore** доведён: collector-hook + global→terminate middleware + apcu in-memory fallback (4 доп. коммита).
- **2026-05-25 — rusaifin**: Sentry + /metrics + active_sessions + json log channel. Core-gateway/dualwrite метрики **отложены** (CoreApiClient активно меняется на cutover-final D2 — инструментация на dev = конфликт при merge).

## ⚠️ Сохранённый чужой WIP (требует внимания автора)

Я работал на feature-ветках от origin/dev. В рабочих деревьях нашёл незакоммиченные изменения — изолировал, **ничего не потеряно**, но автору надо разрулить:

- **rusaiauth:** `docker/Dockerfile` vite-builder stage → **stash@{0}** (`track-b: preserve author WIP vite-builder`). При pop возможен тривиальный merge с моей apcu-строкой (разные регионы файла).
- **rusaisklad_back:** doc-реорг (53 удаления + 3 новых docs) → **stash@{0}** (`track-b: preserve author doc-reorg WIP`).
- **rusaifin:** в рабочем дереве ветки `feature/track-b-instrumentation` остались **незакоммиченные** правки `app/Http/Controllers/Project/{PointController,ProjectController}.php` (D2 `CoreScopeResolver` reader-switch). Их НЕТ ни в origin/dev, ни в committed cutover-final, ни (полностью) в stash — похоже, параллельная работа автора. Я **намеренно исключил** их из своего obs-коммита (soft-reset + unstage) и оставил нетронутыми. Реши, куда их девать (вероятно — на cutover-final). cutover-final-WIP rusaifin (CoreApiClient/services/cutover-миграции + 2 теста) лежит в rusaifin **stash@{0}**.

## Known follow-ups (не решаю сам)

- **rusaifin Core-gateway метрики** (core_api latency, dualwrite_fallback) отложены — добавить когда D2/D6 приземлятся (CoreApiClient на cutover-final).
- **rusaifin dev↔cutover-final разошлись** (D2). После приземления B в main + pull в cutover-final понадобится merge `dev→cutover-final` (или явный отказ + sync позже). Не трогаю cutover-final в этом треке.
- **rusaifin `origin/main` содержит чужие незадеплоенные коммиты** (Track C heads-up: Magnit metrics, ShiftService, redirect + миграция). При merge B в main и pull на prod подтянутся вместе — согласовать с автором тех коммитов.
- **rusaicore deploy от root падает по SSH** (deploy-key у user `Rusaicore`) — workaround `runuser -u Rusaicore`.

## От пользователя нужно (deploy-фаза)

- **Telegram:** bot token + chat id (через @BotFather). В memory/файлы не пишем.
- **UptimeRobot:** аккаунт/API-ключ ИЛИ ручное заведение 4 мониторов: Grafana, `https://sso.rusaifin.ru`, `https://fintech.rusaifin.ru`, `https://rusaisklad.ru`.
