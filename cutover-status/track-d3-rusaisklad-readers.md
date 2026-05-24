# Track D3 — rusaisklad reader switch

**Status:** done (код на ветке `cutover-final`, не мерджен в dev/main — для D7/Track E)
**Owner chat:** dolgan / 2026-05-24 session
**Last update:** 2026-05-25

## Цель

Переключить rusaisklad_back с адаптерного `Domain/Core/`-слоя, читающего **локальные
shadow-таблицы** (`users` / `projects` / `memberships`), на **реальные Core gateway
calls** (D1 bulk-эндпоинты). Вся работа — ветка `cutover-final` в rusaisklad_back.
**Не мерджить в dev/main до D7/Track E.**

## Реестр Domain/Core/ (разведка 2026-05-24)

Слой построен под этот свитч заранее: 3 контракта + 2 реализации (`Local*` shadow и
`Core*Gateway`). Сейчас в `AppServiceProvider::register()` контракты привязаны к `Local*`.

| Контракт | Текущая реализация (shadow) | Читает локально | Целевой Core endpoint (D1) |
|---|---|---|---|
| `EmployeeDirectory` | `LocalEmployeeDirectory` | `users` (name/phone/email) | `GET /v1/employees` — **bulk gap, см. ниже** |
| `ProjectCatalog` | `LocalProjectCatalog` | `projects` (code/name) | `GET /v1/projects` — `filter[external_ids][]`/`filter[code]` ✅ |
| `ProjectMembershipProvider` | `LocalProjectMembershipProvider` | `memberships` (role) | `GET /v1/project-memberships` — `filter[employee_external_id]` + `filter[project_external_ids][]` ✅ |

**Gateways (есть, но пока только для shadow-sync):** `CoreEmployeeGateway::listAll()`,
`CoreProjectGateway::listAll()`, `CoreProjectMembershipGateway::listActiveForProject()`.
Транспорт — `CoreApiClient` (OAuth client_credentials, pagination, retries). Готов.

**Anchor-колонки (остаются локальными, читать их — НЕ shadow-чтение домена):**
- `users.core_employee_external_id` (`User::CORE_EMPLOYEE_EXTERNAL_ID_COLUMN`)
- `projects.core_project_external_id`
Нужны для local int id ↔ external UUID маппинга: все ~8 потребителей контрактов
передают **локальные int id** (`$user->id`, `$project->id`), а inventory-FK ссылаются
на локальные `users.id`/`projects.id`. Эти строки убрать нельзя — убираем только
чтение Core-доменных атрибутов (name/code/role) из shadow-копий.

## Потребители контрактов (8 файлов)

- `Services/Inventory/{InventoryReportService,InventoryDocumentService,InventoryService}` — `ProjectMembershipProvider` (getRole/hasMembership)
- `Services/Projects/CurrentProjectService` — `ProjectCatalog` + `ProjectMembershipProvider`
- `Services/User/UserReadService` — все 3 (уже с in-request memo-полями)
- `Http/Controllers/API/Inventory/InventoryTransferController` — `ProjectMembershipProvider`
- `Domain/Auth/Services/{RoleService,AuthorizationService}` — membership + employee
- `Domain/Auth/Policies/UserPolicy` — `ProjectCatalog::findByLocalId`

## Core endpoint capability (сверено по rusaicore@cutover-final)

- `GET /v1/projects`: `filter[external_id]`, `filter[external_ids][]` (≤100), `filter[code]`, `filter[status]` ✅
- `GET /v1/project-memberships`: `filter[employee_external_id]` (single) + `filter[project_external_ids][]` (≤100) ✅
- `GET /v1/employees`: `filter[external_id]` (single), `filter[identity_user_id]`, `filter[email]`, `filter[status]` — **НЕТ `filter[external_ids][]`** (D1 его не добавлял).

## Scope-решения (ПОДТВЕРЖДЕНЫ автором 2026-05-24)

1. **EmployeeDirectory bulk gap → расширить D1 (вариант A).** Добавить `filter[external_ids][]`
   (≤100) в Core `/v1/employees` — симметрично `/v1/projects`, та же ветка `cutover-final`
   rusaicore. Обновить D1 status + спеку `02-core-extend.md` секция 4a + OpenAPI.
   `EmployeeDirectory` переключается на Core полностью.
2. **Writer scope → readers + включить disable-флаги (вариант 2).** sklad становится
   read-only по projects/memberships: `core.stage1.disable_local_project_writes` и
   `..._membership_writes` ON на ветке cutover-final. Локальные write-эндпоинты
   (`addToProject`/`updateInProject`/`destroyInProject`, `ProjectController::store/update/destroy`)
   отдают guard-ошибку. sklad-write-via-Core — отдельный sub-track (НЕ в D3).

## Что сделано (итог)

**rusaicore @ cutover-final** (расширение D1, Решение 1): `GET /v1/employees` получил
`filter[external_ids][]` (≤100). Commit `b2154df`. См. track-d1 status.

**rusaisklad_back @ cutover-final** (создана от `dev` = `1a2d4bc`), commit `b1c095b`:

- **`app/Domain/Core/Projection/`** — новый слой Core-backed реализаций:
  - `LocalExternalIdMap` (scoped) — резолв local int id ⇄ external UUID через anchor
    `users.external_user_id` / `projects.core_project_external_id` (link, НЕ shadow-домен),
    memo + batch-prime в обе стороны.
  - `CoreProjectCatalog` / `CoreEmployeeDirectory` / `CoreProjectMembershipProvider`
    реализуют 3 контракта, читают из Core, маппят обратно в `*View` с локальными id.
- **Gateways** расширены batch read-методами поверх `CoreApiClient`:
  - `CoreProjectGateway::{findByExternalId,findByCode,findByExternalIds}` (chunk 100)
  - `CoreEmployeeGateway::{findByExternalId,findByExternalIds}` (chunk 100)
  - `CoreProjectMembershipGateway::{listOpenForEmployee,listOpenForProject}`
    (`filter[employee_external_id|project_external_id]` + `is_open=1`)
- **`AppServiceProvider`**: контракты перепривязаны `Local*` → `Core*`, биндинг `scoped`
  (+ `LocalExternalIdMap` scoped) — общий in-request memo на всех потребителей.
- **Writer scope** (решение 2): `config/core.php` дефолт `disable_local_project_writes` /
  `disable_local_membership_writes` → `true`; `.env.example` выставлен. sklad read-only
  по projects/memberships (guard'ы `guardLocalProjectWrites`/`guardLocalMembershipWrites`
  уже были в `ApiController`). sklad-write-via-Core — **отдельный sub-track** (НЕ в D3).
- **N+1 guard**: `getRole`/`hasMembership` в циклах (InventoryReportService и др.) больше
  не порождают HTTP-на-вызов — полный список членств employee/project тянется 1 раз и
  memo'ится.

## Тесты

- **Новые: `tests/Feature/Core/CoreReaderSwitchTest` — 8/8 PASS.** Full chain (impl →
  gateway → CoreApiClient → `Http::fake`), стаб S2S токен-провайдера: чтение атрибутов из
  Core по local id, bulk `filter[external_ids][]` + маппинг local id, role/hasMembership,
  `is_open`/`employee_external_id` в query, list→localProjectId маппинг, N+1-memoization
  (повторные getRole = 1 HTTP), graceful null без anchor (0 HTTP). Pint clean.
- Binding-smoke: контракты резолвятся в `Core*` (tinker), приложение грузится без ошибок.

## ⚠️ Heads-up — pre-existing feature-suite breakage (НЕ регрессия D3)

Полный suite: **105 failed / 11 skipped / (71 passed)**. Эти 105 **идентичны** baseline на
чистом `dev` (Local-биндинг, guards off) — провал **пред-существующий**, не от D3:
- `InventoryApiTest` (~74), `BusinessApiTest`, `SkuApiTest`, `DocumentGenerationTest`,
  `IContactSyncApiTest` — Sanctum-эпоха, сломаны OAuth-cutover'ом. CLAUDE.md: «переписать
  через trait `AuthenticatesAsOAuthUser`» (которого в sklad ещё НЕТ).
- `CoreApiClientTest` (2 failed) — делает реальный HTTP к токен-эндпоинту `:8002`
  (недоступен в тестах); environmental, не мокает токен-провайдер.

**Acceptance «все feature-тесты зелёные» заблокирован этим долгом** — это отдельная
test-infra задача (создать trait + переписать feature-тесты), вне scope D3. Мой свитч
проверен прицельным CoreReaderSwitchTest. Рекомендация: завести sub-track «sklad test
infra (AuthenticatesAsOAuthUser trait)» перед Track E rehearsal.

## Blocked

- —

## Next

- `cutover-final` (rusaisklad_back + rusaicore) **не мерджить** в dev/main до D7/Track E.
- Push — по команде автора (по умолчанию НЕ пушу).
- Отдельные sub-track'и (обсудить с автором): (1) sklad-write-via-Core; (2) sklad test
  infra trait для зелёного feature-suite.
- Phase 5 cleanup: удалить vestigial `read_*_from_projection` config + env-ключи;
  рассмотреть выпил `Domain/Core/Local/*` shadow-реализаций (после доказательства D7).

## Artifacts

- rusaicore (ветка `cutover-final`): commit `b2154df` (employees bulk).
- rusaisklad_back (ветка `cutover-final`): commit `b1c095b` — 11 файлов
  (`app/Domain/Core/Projection/*` ×4, 3 gateway, `AppServiceProvider`, `config/core.php`,
  `.env.example`, `tests/Feature/Core/CoreReaderSwitchTest`). Локально, без push.
- root repo (main): этот status-файл.
- ⚠️ В working tree sklad на `dev` были пред-существующие незакоммиченные удаления ~53
  root-`*.md` + untracked `docs/{INVENTORY,OPERATIONS,REPORTS}.md` (чужой WIP) — в коммит
  D3 НЕ включены, не трогались.
