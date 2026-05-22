# Final Stage Cutover Cleanup — Sprint Plan

**Дата создания:** 2026-05-21
**Дата завершения:** TBD
**Цель:** одним big-bang cutover-окном закрыть всё, что осталось висеть после M2 / Stage 1 / Stage 2 α, привести систему в состояние «можно строить новые фичи (rusairegistry) без архитектурных компромиссов и shadow-таблиц».

## Принципы

1. **Один big-bang cutover** на весь пулл работ (ADR-0003). Никаких feature flags, никаких поэтапных окон.
2. **Phase 0 — observability** — отдельный pre-window stage, обязательный prerequisite. Без observability в cutover-окно не идём.
3. **Параллельное выполнение** через несколько Claude Code chat'ов. 2 параллельно — оптимум, 3 — потолок.
4. **Каждый track self-contained:** свой kickoff prompt, свои acceptance criteria, свой файл статуса в `/cutover-status/`.

## Общая схема

```
Phase 0 — Observability (Track A + B)        ── parallel ──┐
Phase 1 — Pre-window tech debt (Track C)     ── parallel ──┤
                                                            │
                            sync: observability live, неделя baseline
                            sync: Track C закрыт
                                                            │
Phase 2 — Cutover code prep (Track D)        ── ветка cutover-final
   D1 (bulk endpoints) → D2 (fin readers) ┐
                       → D3 (sklad readers) ├── parallel
                       → D4 (fin writers)   ┘
   D5 (legacy archive scripts)             ── parallel со всем
   D6 (drop dual-write) → D7 (acceptance)  ── после D4
                                                            │
                            sync: D7 зелёный на dev
                                                            │
Phase 3 — Dev rehearsal (Track E)            ── single chat
                                                            │
                            sync: rehearsal зелёный
                                                            │
Phase 4 — Prod cutover window (Track F)      ── single chat
                                                            │
Phase 5 — Post-window stabilization (Track G)── single chat
```

## Tracking прогресса

Каждый track имеет свой файл в `/cutover-status/`. Формат и конвенция — `/cutover-status/README.md`.

Команда сводки:
```bash
grep -A1 "Status:" /home/dolgan/russ360/cutover-status/*.md
```

---

## Phase 0 — Observability bootstrap

**Зачем:** глаза на cutover-окно. Без baseline metrics и работающих alerts мы войдём в самую рискованную операцию слепыми.

**Acceptance gate Phase 0:** observability stack live на prod, неделя baseline metrics накоплена, alerts откалиброваны (false positive rate < 10%), Telegram bot отвечает, UptimeRobot пингует.

### Track A — Observability infrastructure

**Цель:** поднять stack из 6 компонентов на одном сервере через docker-compose в новой директории `infra/observability/`.

**Состав:**
- Prometheus (метрики, scrape config для всех сервисов)
- Node Exporter (метрики хоста)
- Loki (логи, хранилище)
- Promtail (log shipper с docker и host-rusaifin)
- Grafana (UI + provisioning из git)
- GlitchTip (Sentry-compatible exception tracking)

**Зависимости:** —

**Acceptance:**
- `infra/observability/compose.yml` поднимает stack локально (dev-rehearsal).
- Grafana доступна локально на `:3030` (или выбранном порту), логин admin/admin.
- Prometheus собирает свои метрики + Node Exporter с хоста.
- Loki принимает логи через Promtail.
- GlitchTip принимает test-issue через Sentry SDK.
- Provisioning из `infra/observability/grafana/provisioning/` восстанавливает dashboards при rebuild.
- На prod-сервере 82.146.57.149 поднят аналогичный stack, доступен через nginx vhost `https://observability.rusaifin.ru` (или подобный) с basic auth.

**Sync output:** prod-URL Grafana, GlitchTip DSN на каждый сервис, Prometheus scrape config endpoint.

**Kickoff prompt:**

> Поднимаешь observability stack для Russ360 в новой директории `/home/dolgan/russ360/infra/observability/`. Контекст и acceptance — `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 0, Track A). Состав: Prometheus + Node Exporter + Loki + Promtail + Grafana + GlitchTip — docker-compose, provisioning из git, базовые dashboards (host CPU/RAM/disk, per-service request rate / latency / errors).
>
> Шаги: (1) спроектируй структуру директории, покажи мне план compose-файла + provisioning. (2) После моего «иди» — поднимай локально, smoke. (3) После «иди на dev» — деплой на dev. (4) После «иди на прод» — деплой на prod через ssh root@82.146.57.149.
>
> Статус-файл: `/cutover-status/track-a-observability-infra.md` — создай в начале, обновляй в конце каждой сессии.
>
> ADR-0004 уже обновлён — observability принят. Не предлагать альтернативы (k8s, SaaS solutions).

### Track B — Application instrumentation

**Цель:** проинструментировать 4 backend + 2 фронта так, чтобы они отдавали метрики и шипели логи в observability stack из Track A.

**Состав:**
- Sentry SDK (PHP) в каждом из 4 backend, DSN → GlitchTip
- Sentry SDK (Vue/Nuxt) в обоих фронтах
- Laravel exporter middleware в каждом backend (request rate, latency histogram, error rate) — `spatie/laravel-prometheus` или самописный
- Structured logging config (JSON formatter) для лучшего парсинга в Loki
- Custom business metrics (по выбору): количество active sessions, dual-write fallback rate, Core API latency

**Зависимости:** Track A должен иметь поднятый Prometheus и GlitchTip (DSN endpoints).

**Acceptance:**
- В Grafana видны 4 backend и 2 фронта с request rate / latency / errors.
- В GlitchTip видны test-exceptions из каждого сервиса.
- В Loki видны логи всех 4 backend.
- Базовые alerts настроены: 5xx rate > 1%, request latency p95 > 1s, error rate > 5/min в GlitchTip, host disk > 80%.
- Alerts уходят в Telegram (через Grafana Contact Point).
- UptimeRobot настроен на: Grafana URL, SSO URL, оба фронта prod.

**Sync output:** список endpoints, dashboards URLs, alert rules в коде (`infra/observability/grafana/provisioning/alerting/`).

**Kickoff prompt:**

> Инструментируешь Russ360 для отправки метрик/логов/exceptions в observability stack из Track A. Контекст — `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 0, Track B). 4 backend + 2 фронта.
>
> Перед стартом проверь: Track A статус (`cat /home/dolgan/russ360/cutover-status/track-a-observability-infra.md`). Если не done — спроси у меня, продолжать ли (нужны DSN endpoints).
>
> Состав: Sentry SDK в каждом сервисе → GlitchTip, Laravel exporter middleware → Prometheus, structured JSON logging для Loki, базовые alerts, Telegram bot, UptimeRobot.
>
> Шаги: (1) покажи план интеграций по каждому сервису. (2) После «иди» — реализуй по одному сервису, тесты в каждом, smoke локально. (3) После «иди на dev» — деплой на dev. (4) После «иди на прод» — на prod.
>
> Статус-файл: `/cutover-status/track-b-app-instrumentation.md`.

### Sync point Phase 0 — неделя baseline

После Track A + B live на prod — **неделя сбора baseline**. В этот период:
- Calibrate alert thresholds (что считать «нормой»)
- Тренироваться смотреть dashboards
- Найти и пофиксить false-positive alerts
- Тренироваться в Telegram — реагировать на alerts

В это время **можно начать Phase 1 (Track C) и/или Phase 2 prep (Track D1, D5)** в параллель — они не требуют observability.

---

## Phase 1 — Pre-window technical debt

**Зачем:** убрать мелкие долги отдельными деплоями ДО cutover-окна, чтобы окно было сфокусированным.

**Acceptance gate Phase 1:** все 4 item Track C закрыты, каждый отдельным deploy через обычный dev→main flow (не через cutover-final ветку).

### Track C — Pre-window technical debt

**Цель:** закрыть независимые мелкие долги.

**Состав (каждый — самостоятельный mini-task):**
- **C1.** `rusaiauth_reader` PostgreSQL role вместо superuser в `RUSAIAUTH_DB_*` env rusaifin и rusaisklad.
- **C2.** bibli pipeline fix для rusaisklad_front prod docker build (см. memory `rusaisklad_front_bibli_docker_blocker`).
- **C3.** APP_DEBUG=true на rusaifin prod — решение: ADR'ить «остаётся включённым» с обоснованием, ИЛИ выключить + fix.
- **C4.** Duplicate points 66/202 data fix в rusaifin (см. memory `rusaifin_duplicate_points_66_202`).

**Зависимости:** —

**Acceptance:** каждый item имеет свой commit на main + deploy на prod + verification.

**Sync output:** PR / commit refs на каждый item, статусы на prod.

**Kickoff prompt:**

> Закрываешь pre-window technical debt из `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 1, Track C). 4 независимых item: rusaiauth_reader role, bibli fix, APP_DEBUG решение, duplicate points.
>
> Бери по одному, в любом порядке. Каждый = отдельный коммит на main + deploy. Не сваливать в один PR.
>
> Контекст по каждому item — в memory:
> - C1: `[[oauth_clients]]` + `m2_prod_cutover_done` post-cutover TODO
> - C2: `[[rusaisklad_front_bibli_docker_blocker]]`
> - C3: `[[rusaifin_prod_debug_intentional]]`
> - C4: `[[rusaifin_duplicate_points_66_202]]`
>
> Статус-файл: `/cutover-status/track-c-pre-window-tech-debt.md`.

---

## Phase 2 — Cutover code prep

**Зачем:** подготовить ВЕСЬ код cutover'а на одной ветке `cutover-final`. Ничего в dev/main до acceptance D7.

**Acceptance gate Phase 2:** D7 acceptance test suite зелёный, все 4 backend на ветке `cutover-final` собираются, dev-cutover на dev-БД прошёл (Track E).

### Track D — Cutover code prep

Все sub-tracks D1-D7 ведутся на ветке `cutover-final` во всех 4 backend репо.

#### D1 — Core API bulk endpoints

**Цель:** добавить bulk-эндпоинты в rusaicore, чтобы reader switch не создавал N+1 проблему.

**Состав:**
- `GET /v1/operational-locations?ids[]=...` (батч до 100)
- `GET /v1/projects?ids[]=...`
- `GET /v1/project-memberships?employee_id=...&project_ids[]=...`
- `GET /v1/operational-location-assignments?location_ids[]=...&open=true`
- Eager-load включения в одном запросе (`?include=project,assignments`)

**Зависимости:** —

**Acceptance:** все эндпоинты + integration тесты + OpenAPI/markdown спека обновлена.

**Sync output:** список новых эндпоинтов, формат query.

#### D2 — rusaifin reader switch

**Цель:** переключить все читатели `project_points` / `projects` / `project_point_agents` / `project_user` в rusaifin на Core gateways.

**Состав:**
- Реестр контроллеров (grep по таблицам) — артефакт `cutover-status/track-d2-controllers-registry.md`
- Реестр domain services и API resources
- Замена Eloquent ORM-запросов на Core gateway calls
- In-request memoization для справочников (предотвратить запросы одних и тех же объектов в одном HTTP request)
- Адаптация контроллерных responses к Core DTO
- Полная замена feature-тестов через trait + mock Core gateways

**Зависимости:** D1 (bulk endpoints должны быть).

**Acceptance:**
- `grep -rn "ProjectPoint::\|Project::\|ProjectPointAgent::\|->projects()\|->points()" rusaifin/app/` возвращает только bootstrap code / writers (которые D4 заменит).
- Все feature-тесты зелёные.
- Smoke: admin login, /agents, /points, /map, /reports — работают на mocked Core.

**Sync output:** список переключенных контроллеров, новые тесты.

#### D3 — rusaisklad reader switch

**Цель:** переключить sklad с адаптерного `Domain/Core/` слоя на реальные Core gateways.

**Состав:**
- Реестр читателей sklad (меньше чем у fin, sklad с самого начала писан с Core в виду)
- Замена адаптерных классов на gateway calls
- Адаптация sklad UI flows

**Зависимости:** D1.

**Acceptance:**
- Sklad больше не читает локальную shadow-копию данных Core.
- Все feature-тесты зелёные.

**Sync output:** список переключенных classes.

#### D4 — rusaifin writer switch

**Цель:** переключить writes из `PointService` (`attachAgent`, `detachAgent`, `setLeader`, etc.) с legacy + best-effort dual-write на Core authoritative.

**Состав:**
- `PointService` пишет ТОЛЬКО в Core через `CoreOperationalLocationAssignmentWriteGateway`.
- Legacy таблицы `project_point_agents` / `project_user` становятся **read-only** (см. D5).
- Backfill пропущенных событий за окно cutover (если будут).

**Зависимости:** D2 (readers должны переключиться на Core до того, как writers перестанут писать в legacy — иначе UI временно будет показывать stale data).

**Acceptance:**
- В `PointService` нет вызовов legacy Eloquent моделей.
- Все writes идут через Core gateway, ошибки больше не молчат (raise exception).
- Feature-тесты зелёные.

**Sync output:** diff PointService, список Core endpoints.

#### D5 — Legacy archive scripts

**Цель:** подготовить SQL-скрипты для archive легаси таблиц (`project_points`, `project_point_agents`, `projects`, `project_user`).

**Состав:**
- READ-ONLY триггеры на INSERT/UPDATE/DELETE (raise exception в момент cutover'а)
- Опционально: переименование в `*_legacy` для явности
- Скрипт обратной миграции (rollback)

**Зависимости:** — (можно параллелить со всем).

**Acceptance:** скрипты лежат в `rusaifin/database/migrations/cutover/` (не запускаются автоматом), dry-run на dev прошёл.

**Sync output:** SQL скрипты, rollback procedure.

#### D6 — Drop dual-write

**Цель:** удалить весь best-effort dual-write код из rusaifin.

**Состав:**
- Удалить try/catch с 409 swallowing
- Удалить fallback writes в legacy
- Удалить `core_location_external_id` синхронизацию (теперь Core authoritative)
- Удалить мониторинг dual-write rate

**Зависимости:** D4 (writers полностью на Core).

**Acceptance:** `grep -rn "dual-write\|best-effort\|swallowed.*409" rusaifin/app/` пусто.

**Sync output:** diff cleanup.

#### D7 — Acceptance test suite

**Цель:** end-to-end test suite, который проверяет, что после cutover всё работает.

**Состав:**
- E2E: login admin → создать проект → добавить точку → привязать агента → отвязать → удалить
- E2E: login agent → видеть свои точки → видеть assignments
- E2E: login leader → видеть подчинённых агентов
- Smoke API: все Core endpoints отвечают
- Smoke fin/sklad: HTTP 200 на критических роутах
- Smoke observability: метрики приходят, alerts работают

**Зависимости:** D6 (полный cutover code на месте).

**Acceptance:** все тесты зелёные на dev с restored prod-dump.

**Sync output:** test results report, который заархивирован как baseline.

**Kickoff prompt для Track D (общий):**

> Готовишь cutover code на ветке `cutover-final` в репо rusaicore, rusaifin, rusaisklad_back, fintech (front), rusaisklad_front. Контекст — `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 2, Track D, sub-tracks D1-D7).
>
> Зависимости между sub-tracks — в плане. Не нарушать порядок (D1 → D2/D3, D4 после D2, D6 после D4).
>
> ВАЖНО: ВСЁ на ветке `cutover-final`. **Не мерджить в dev/main** до acceptance D7.
>
> Memory check перед стартом:
> - `[[git_workflow_dev_main]]` — push в dev, merge в main только по команде
> - `[[cutover_stage_2_branch]]` — ветка cutover-final = переименованная cutover-stage-2 со scope final
> - `[[stage2_partial_predeploy_prod]]` — что уже в prod (Stage 2 α)
>
> Статус-файлы: `/cutover-status/track-d1-bulk-endpoints.md`, `track-d2-fin-readers.md`, ..., `track-d7-acceptance.md`.
>
> Для D2 — параллельно с D3 (разные сервисы). D5 параллельно со всеми.

---

## Phase 3 — Dev rehearsal

### Track E — Dev cutover rehearsal

**Цель:** прогнать полный cutover на dev-БД (restored from prod-dump), найти грабли, починить.

**Зависимости:** Phase 2 закрыт (D7 зелёный).

**Acceptance:**
- Полный dev-cutover окно от старта до acceptance < 90 минут (целевая длительность prod-окна).
- 0 регрессий в smoke checklist.
- Все 4 backend и 2 фронта работают после dev-cutover.
- Rollback процедура отрабатывается на dev (минимум 1 раз).

**Sync output:** findings list → если есть фиксы → patches → re-rehearsal.

**Kickoff prompt:**

> Прогоняешь dev-rehearsal Final Stage Cutover. Контекст — `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 3, Track E).
>
> Перед стартом: Phase 2 (D7) должен быть `done` в статус-файле. Если нет — стоп, спроси.
>
> Шаги: (1) refresh dev из prod через `/root/refresh-dev-from-prod.server.sh`. (2) merge `cutover-final` → dev во всех 5 репах. (3) deploy на dev-сервер. (4) полный smoke checklist (admin + agent + leader сценарии, observability, sklad UI). (5) если findings — стоп, патч, re-rehearsal. (6) обязательно прогнать rollback (revert dev на pre-cutover SHA).
>
> Статус-файл: `/cutover-status/track-e-dev-rehearsal.md`.

---

## Phase 4 — Prod cutover window

### Track F — Production cutover

**Цель:** THE event. Cutover на prod в одном окне.

**Зависимости:** Track E зелёный, Phase 0 baseline accumulated, Phase 1 закрыт.

**Sequence в окне (целевое < 90 минут):**

1. **T0** Pre-flight verify: дашборды Grafana открыты, Telegram канал прочищен от noise, дампы свежие (свежее 2 часов), reconcile orphans = 0, дежурство на чате.
2. **T0+5** Maintenance window: rusaifin nginx 503 на write-эндпоинты (read остаётся). Telegram: «начинаем».
3. **T0+10** Final backfill sync (если нужен).
4. **T0+15** Merge `cutover-final` → main во всех 5 репах + push.
5. **T0+20** Deploy на prod: pull main на всех сервисах + composer/npm install + caches rebuild + миграции (если есть в обычной папке) + restart php-fpm.
6. **T0+40** Apply legacy archive (D5 SQL) — переводим legacy таблицы в read-only.
7. **T0+50** Smoke critical paths: admin + agent + leader.
8. **T0+70** Снимаем maintenance, unfreeze writes. Telegram: «закончили, мониторим».

**Rollback процедура (если smoke падает после T0+50):**
- Maintenance window remains
- Reset main на pre-cutover SHA в каждом репо
- Composer/npm install + caches
- Restore dumps если требуется
- Снимаем legacy archive triggers
- Restart, smoke, unfreeze

**Acceptance в окне:**
- HTTP 200 на критических роутах
- 0 5xx за 10 минут после snimaem maintenance
- Telegram alerts не звенят
- Grafana показывает baseline-shaped trafic

**Sync output:** cutover SHA на каждом сервисе, время старта/конца, findings → Phase 5.

**Kickoff prompt:**

> Выполняешь Final Stage Cutover на prod. Контекст — `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 4, Track F).
>
> ВАЖНО: это PROD операция. Перед каждым шагом — статус апдейт в Telegram-канал и в `/cutover-status/track-f-prod-cutover.md`. На каждый шаг — ждать моего «иди».
>
> Перед стартом проверь:
> - Track E `done`?
> - Phase 0 baseline неделя прошла?
> - Phase 1 закрыт?
> - Dump'ы свежие (< 2 часа)?
>
> Если что-то «нет» — стоп.
>
> Memory check: `[[prod_infrastructure]]`, `[[infra_map]]`, `[[git_workflow_dev_main]]`.
>
> Статус-файл: `/cutover-status/track-f-prod-cutover.md` обновляешь после КАЖДОГО шага последовательности.

---

## Phase 5 — Post-window stabilization

### Track G — 24h monitoring + cleanup

**Цель:** убедиться, что после окна нет хвостовых проблем, добить cleanup, освежить документацию.

**Зависимости:** Track F закрыт успешно.

**Состав:**
- 24 часа активного мониторинга Grafana / GlitchTip / Telegram alerts
- Reconcile прогон через 24 часа (orphans = 0)
- Удалить применённые миграции из `database/migrations/cutover/` во всех сервисах
- Удалить ветку `cutover-final` локально и на remote (после tag'а)
- Tag коммит final cutover: `git tag -a final-stage-cutover -m "Final Stage Cutover 2026-MM-DD"` во всех 5 репах
- Освежить `docs/russ360-deep-dive.md` (он pre-cutover snapshot 2026-05-04)
- Архивировать `docs/russ360-audit-2026-05-18.md`, написать свежий audit
- Memory cleanup: архивировать `[[stage2_*]]` memory, написать `final_stage_cutover_done`
- Удалить ad-hoc workaround'ы (если есть) с prod
- Решить судьбу `docs/russ360-stage2-playbook.md` (архивировать или влить в новый playbook'у)

**Acceptance:**
- 24 часа без incident'ов в Telegram
- Все cleanup items выполнены
- Документация обновлена

**Sync output:** список tag'ов, обновлённая документация.

**Kickoff prompt:**

> Закрываешь Final Stage Cutover — Phase 5 (Track G). Контекст — `docs/final-stage-cutover-cleanup-sprint-plan.md`.
>
> Шаги: 24h monitoring → reconcile → cleanup migrations → tag → docs refresh → memory cleanup.
>
> Memory check: `[[m2_prod_cutover_done]]` post-cutover TODO список — пройди и закрой что осталось открытого.
>
> Статус-файл: `/cutover-status/track-g-post-window.md`.

---

## Acceptance gate — Stage Final Cutover Done

Закрываем cutover, когда **все** выполнены:

- **Код:** в rusaifin/sklad нет ни одного прямого чтения `project_points` / `projects` / `project_point_agents` / `project_user`. Только через Core gateways.
- **Writes:** Core authoritative. Dual-write best-effort код полностью удалён.
- **Legacy:** таблицы либо в read-only режиме (INSERT triggers raise), либо удалены.
- **Security:** `rusaiauth_reader` role, не superuser. APP_DEBUG решено. Все 4 item Track C закрыты.
- **Observability:** stack live минимум месяц на prod, alerts откалиброваны, false positive < 10%.
- **Документация:** свежий deep-dive, свежий audit, ADR-0001 «Status: still accepted» подтверждён.
- **0 межсервисных HTTP timeouts** в неделю prod-наблюдения (без backfill-нагрузок).

После Acceptance Gate — **чистый старт для rusairegistry**.

---

## Как использовать этот план с Claude Code

### Стартовать новый track в новом chat'е

1. Открываешь новый chat Claude Code.
2. Копируешь **kickoff prompt** из соответствующей секции плана.
3. Дополнительно говоришь «работаешь над Track X из плана `docs/final-stage-cutover-cleanup-sprint-plan.md`».
4. Chat читает план, читает свой статус-файл, проверяет зависимости — и идёт.

### Параллельность

- 2 chat'а одновременно — sane.
- 3 chat'а — максимум.
- Не запускай chat'ы на треки, которые трогают одни и те же файлы.

### Sync points

После завершения трека — обязательное обновление `/cutover-status/<track>.md` со статусом `done`. Зависимые треки проверяют его через `cat /home/dolgan/russ360/cutover-status/track-X-*.md` перед стартом.

### Если chat умирает / контекст переполнился

Следующий chat читает свой статус-файл (`/cutover-status/<track>.md`), `git log` своей ветки и продолжает с того места, где предыдущий остановился. Статус-файл — crash-recovery механизм.

### Эскалация

Если track blocked > 1 рабочий день — обязательно сообщи в чат, разбираем root cause, не игнорируем.

---

## Связанные документы

- [ADR-0001](adr/0001-deliberate-service-oriented-architecture.md) — SOA foundational
- [ADR-0003](adr/0003-big-bang-cutovers.md) — почему big-bang
- [ADR-0004](adr/0004-what-we-do-not-do.md) — observability триггер сработал 2026-05-21
- `docs/russ360-stage2-playbook.md` — старый Stage 2 playbook (будет архивирован в Phase 5)
- `docs/russ360-audit-2026-05-18.md` — состояние системы перед cutover
- `cutover-status/README.md` — конвенция статус-файлов

---

**Owner:** dolgan
**Last update:** 2026-05-21
