# Track D1 — Core API bulk endpoints

**Status:** done (код на ветке `cutover-final`, не мерджен в dev/main — это для D7/Track E)
**Owner chat:** dolgan / 2026-05-24 session
**Last update:** 2026-05-24

## Цель

Добавить bulk-фильтрацию + eager-loading в `rusaicore`, чтобы reader switch (D2 rusaifin / D3 rusaisklad) не порождал N+1. Вся работа — ветка `cutover-final` в rusaicore. **Не мерджить в dev/main до D7.**

## Скоуп (5 пунктов плана)

1. `GET /v1/operational-locations` — батч по `external_ids[]` (до 100)
2. `GET /v1/projects` — батч по `external_ids[]`
3. `GET /v1/project-memberships` — `employee_external_id` + `project_external_ids[]`
4. `GET /v1/operational-location-assignments` — `operational_location_external_ids[]` + `is_open`
5. `?include=project,assignments` eager-loading (на operational-locations)

## Решения по контракту (ПОДТВЕРЖДЕНЫ 2026-05-24)

- ✅ Решение 1 → `filter[external_ids][]`-конвенция (рекомендованная).
- ✅ Решение 2 → ветка `cutover-final` от `dev` (47ec28f).

### Решение 1 — query-нотация
План пишет `?ids[]=`, `employee_id=`, `open=true` — это иллюстративно. Реальный контракт Core оперирует `external_id` (UUID) и использует жёсткую `filter[...]`-конвенцию (`ApiListRequest` валит любой top-level ключ кроме `page/per_page/sort/filter`).

**Рекомендация — остаться в существующей конвенции:**
- `?filter[external_ids][]=<uuid>&filter[external_ids][]=<uuid>` (locations, projects)
- `?filter[employee_external_id]=<uuid>&filter[project_external_ids][]=<uuid>` (memberships)
- `?filter[operational_location_external_ids][]=<uuid>&filter[is_open]=true` (assignments)
- `?include=project,assignments` — добавить `include` в whitelist top-level ключей `ApiListRequest`.

### Решение 2 — база ветки cutover-final
`cutover-stage-2` в rusaicore стоит на `390f718` (старее dev, без Track C bonus-фиксов). `dev` = `47ec28f` (с фиксами nginx healthcheck + rusaiauth-net).
**Рекомендация:** создать `cutover-final` от `dev` (свежий стабильный base). Альтернатива — от `cutover-stage-2` (по букве memory `[[cutover-stage-2-branch]]`).

## План реализации

Расширяем существующие `index`-actions (новые роуты не нужны).

**Общая инфраструктура (1 раз):**
- `ApiListRequest`: helper `arrayFilter(string $key, callable $caster)`; whitelist top-level += `include`; helper `includes(): array`.
- Лимит bulk-массива: `filter.<x>_ids` => `array`, `max:100`; `*.* => uuid`. При наличии `external_ids` — auto-bump `perPage` до `min(count, 100)`, чтобы один запрос вернул весь батч.

**По одному endpoint'у, каждый со своими integration-тестами:**
1. operational-locations: `external_ids[]` фильтр → `whereIn('external_id', ...)`.
2. projects: `external_ids[]`.
3. project-memberships: `employee_external_id` (уже есть, single) + `project_external_ids[]` (новый).
4. operational-location-assignments: `operational_location_external_ids[]` + `is_open` (уже есть).
5. `include=project,assignments` на operational-locations: eager-load + условный embed в `OperationalLocationResource` через `whenLoaded`.

**Тесты:** в `tests/Feature/Api/V1/*ApiTest.php` — happy path bulk, лимит >100 → 422, частичное совпадение (несуществующий id игнорируется), `include` возвращает вложенные блоки.

**Документация:** новая секция в `docs/russmarket360/02-core-extend.md` (bulk-фильтры + include) + обновление `openapi/core-mvp1.openapi.yaml`.

**Итог:** локальный smoke на поднятом rusaicore (`docker compose -f rusaicore/compose.yml`), затем обновление этого status-файла.

## Что сделано (итог)

Расширены существующие `index`-эндпоинты (новых роутов нет). Ветка `cutover-final` в rusaicore создана от `dev` (47ec28f).

**Инфраструктура** — `ApiListRequest`:
- helper `arrayFilter()` — читает `filter[x][]` массивы (trim, de-blank, de-dup);
- `include` добавлен в whitelist top-level ключей; helper `includes()`; opt-in `allowedIncludes()` (default `[]`) + валидация неизвестных токенов → 422;
- helper `bulkPerPage()` — при наличии batch-фильтра авто-bump `per_page` до размера батча (cap 100), бóльший явный per_page уважается.

**Эндпоинты (batch-фильтр `filter[...][]`, лимит 100, элементы uuid, неизвестные id молча игнорируются):**
1. `GET /v1/operational-locations` — `filter[external_ids][]`
2. `GET /v1/projects` — `filter[external_ids][]`
3. `GET /v1/project-memberships` — `filter[project_external_ids][]` (+ существующий `filter[employee_external_id]`)
4. `GET /v1/operational-location-assignments` — `filter[operational_location_external_ids][]` (+ существующий `filter[is_open]`)
5. `GET /v1/operational-locations?include=project,assignments` — eager-load + условный embed в `OperationalLocationResource` через requested-includes; без `include` форма ответа не меняется (не breaking).

**Контракт:** `filter[external_ids][]`-конвенция (Решение 1). Идентификатор — `external_id` (UUID).

## Тесты

Integration-тесты на каждый эндпоинт в `tests/Feature/Api/V1/*ApiTest.php`: happy-path batch, `>100 → 422`, non-uuid → 422, неизвестный id игнорируется, full-batch-в-одну-страницу (25 ids при дефолтном per_page=20), include embeds / unsupported include → 422, include=assignments collection.

**Весь suite зелёный: 76 passed (752 assertions).** Pint clean. Живой smoke через реальные Action'ы на dev-БД core (транзакция+rollback): locations bulk=2, projects bulk=1, assignments open=1, include embeds `project`.

## Done
- 2026-05-24: прочитан контекст (Track A/C status, ADR 0001-0004, memory). Обследована архитектура rusaicore API. Составлен план, подтверждены Решения 1+2.
- 2026-05-24: создана ветка `cutover-final` от dev. Реализованы все 5 пунктов скоупа + инфра ApiListRequest. Integration-тесты на каждый. Обновлены спека `02-core-extend.md` (секция 4a) и `openapi/core-mvp1.openapi.yaml`. Suite 76/76, pint clean, smoke зелёный. Закоммичено на `cutover-final`.

## In progress
- —

## Blocked
- —

## Next
- D2 (rusaifin reader switch) / D3 (rusaisklad) могут стартовать — bulk-контракт зафиксирован (см. секцию «Что сделано»). Зависят от этого D1.
- `cutover-final` **не мерджить** в dev/main до D7/Track E (dev-rehearsal).

## Artifacts
- `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 2, D1 — спека)
- rusaicore ветка `cutover-final`, 21 файл (см. commit). Ключевые: `app/Http/Requests/Api/V1/ApiListRequest.php`, `app/Application/*/Actions/List*.php` + `Data/List*Data.php`, `app/Http/Requests/Api/V1/*/List*Request.php`, `app/Http/Resources/{OperationalLocationResource,Concerns/SerializesApiValues}.php`, `docs/russmarket360/02-core-extend.md`, `openapi/core-mvp1.openapi.yaml`, 4× `tests/Feature/Api/V1/*ApiTest.php`.
