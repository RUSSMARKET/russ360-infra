# Track D2 — rusaifin reader switch

**Status:** in-progress (план составлен, ждём «иди» на реализацию)
**Owner chat:** dolgan / 2026-05-24 session
**Last update:** 2026-05-24

## Цель

Переключить читателей legacy-домена (`projects` / `project_points` / пивоты
`project_point_agents` / `project_supports` / `project_regional_directors` / FK
`group_leader_id` / `project_manager_id`) в rusaifin на Core gateways (батч через bulk
endpoints D1). Writes (D4), cross-request Redis-кэш (Phase 5), rename таблиц
(post-acceptance) — **не в скоупе**. Всё на ветке `cutover-final` (поверх 2 коммитов D5),
не мерджить в dev/main до D7, не пушить без команды.

Полный реестр читателей — `track-d2-controllers-registry.md`.

## Разведка (сделано 2026-05-24)

- Прочитан контекст: D1 (контракт bulk), D5 (read-only locks в той же ветке), A, C, ADR 0001–0005,
  memory (`cutover_stage_2_branch`, `git_workflow_dev_main`, `stage2_partial_predeploy_prod`,
  `stage2_put_to_patch_bugfix`, `redis_future_use_cases`, `mysql_trigger_super_1419`).
- Построчный аудит 22 файлов (3 параллельных разведки) → реестр (controllers-registry.md).
- Core read-слой **уже существует** (Stage 2): контракты `OperationalLocationCatalog`/`ProjectCatalog`/
  `ProjectMembershipProvider`/`OperationalLocationAssignmentProvider`/`EmployeeDirectory`, gateways,
  ReadModels, DTOs, DI-биндинги в `AppProvider`. `CurrentProjectService` и `ProjectBootstrapPayloadFactory`
  уже целиком на Core.

## Ключевые находки, повлиявшие на форму плана

1. **ReadModel `$id` = Core int id, не локальный.** Перевод Core-external_id → local int id
   обязателен для JOIN-ов на локальные shifts/reports/products. Мосты:
   `project_points.core_location_external_id`, `users.core_employee_external_id`,
   code `RUSAIFIN_{local_id}` (на `projects` колонки external_id НЕТ).
   → нужен новый **`CoreScopeResolver`** (инкапсулирует перевод + батч-prefetch + memoization).
2. **Часть данных не в Core** (products, `referal`, shift/report-домен) → эти `Point::`/`Project::`
   чтения остаются локальными. Acceptance-grep их будет матчить — ожидаемый residue.
3. **Read-методы read-only батч-эндпоинтов D1** single-id в текущих gateway'ах → добавить
   batch-методы (`listByExternalIds`, `listForOperationalLocationExternalIds`).
4. **In-request memoization** (ТЗ): декоратор поверх gateway'ев, PHP-массив в request scope.
   Redis НЕ тащить (Phase 5, [[redis_future_use_cases]]).

## План (по модулям, каждый — со своими тестами)

### Шаг 0 — инфраструктура (1 раз)
- Batch-методы в read-gateway'ях поверх D1 (`filter[external_ids][]`, cap 100, чанкинг >100):
  `OperationalLocationCatalog::listByExternalIds`, `ProjectCatalog::listByExternalIds`,
  `OperationalLocationAssignmentProvider::listForOperationalLocationExternalIds`,
  (`ProjectMembershipProvider::listForProjectExternalIds` — уже есть).
- **In-request memoization**: декоратор контрактов (request-scoped singleton, array-cache по external_id).
- **`CoreScopeResolver`**: перевод external_id↔local_id (через bridge-колонки + code-конвенцию),
  батч-prefetch. Это санкционированный grep-residue.

### Шаг 1 — Tier 1 (низкий риск): `getProject`, `getPointAgents`, `getUser`
### Шаг 2 — Tier 2 (visibility, критично): `StaffVisibilityScopeService`, `StaffService` access, `ProjectPointAccessService`
### Шаг 3 — Tier 4 (инцидентные): `UserService`, `ProductService`, `NotificationService`, registration controllers
### Шаг 4 — Tier 3 (reports/exports, тяжёлое): metrics service, PlansController reports, 3 Export'а
### Шаг 5 — тесты + smoke + обновление status

## Структура mock'ов для тестов

Существующий паттерн (`ProjectPointAccessHttpContractTest`, `StaffListVisibilityTest`):
in-memory фейки контрактов через `bindCoreContracts()` + `setCoreState(projects, memberships, …)`.
- Вынести общий helper в trait `Tests\Feature\Concerns\FakesCoreReadModels` (фейки 5 контрактов
  + батч-методы + assignments + employees), переиспользовать во всех D2-тестах.
- Сидим локальные anchor-строки (`project_points` с `core_location_external_id`, `users` с
  `core_employee_external_id`) для проверки перевода в `CoreScopeResolver`.

## Acceptance (уточнённый — ПОДТВЕРЖДЁН автором 2026-05-24)

- **Решение 1 (residue) — уточнённый residue.** `grep -rn "ProjectPoint::\|Project::\|ProjectPointAgent::\|->projects()\|->points()" rusaifin/app/`
  возвращает только: (а) bootstrap/writers (D4), (б) `CoreScopeResolver` (id-перевод),
  (в) локально-only домены — products / `referal` / shift-anchor. Пивоты supports/regional_directors —
  только в writers + resolver. Строгий «ноль» отвергнут — требовал бы выноса shifts/products/referal
  в Core (вне D2).
- **Решение 2 (reports tier) — Tier 3 включён в этот проход D2** (reports/exports переключаются
  сразу, не отдельным под-треком). D2 закрывается полным reader-switch.
- Все feature-тесты зелёные.
- Smoke (mocked Core): admin login, `/agents`, `/points`, `/map`, `/reports`.

## Done (реализация)
- **2026-05-24 — Шаг 0a (commit 89d0212):** batch read-методы в Core gateways поверх D1
  (`ProjectCatalog::listByExternalIds`, `OperationalLocationCatalog::listByExternalIds`,
  `OperationalLocationAssignmentProvider::listForOperationalLocationExternalIds`; cap 100, чанкинг).
  Тест `CoreBulkReadGatewayTest`. Заодно устранён pre-existing fatal в `CutoverCommandsTest`
  (фейк без `findActiveAssignmentExternalId`).
- **2026-05-24 — Шаг 0b (commit 405a174):** `CoreScopeResolver` (Domain/Core/Support) —
  мост Core↔local (проект через code `RUSAIFIN_{id}`, локация/сотрудник через bridge-колонки),
  двунаправленные батч-переводы, request-scoped in-request memoization (без Redis).
  Тест `CoreScopeResolverTest` (4). Зарегистрирован `app->scoped`.
- **2026-05-25 — Шаг 1 / Tier 1 (commit 9730112):** `ProjectTeamReader` (PM/РД/саппорты из Core
  memberships), `PointAgentReader` (agents из assignments + leader-point). Переключены
  `ProjectController::getProject`, `PointController::getPointAgents`, `UserController::getUser`.
  Общий mock-слой `tests/Concerns/FakesCoreReadModels` (5 контрактов) + `Tier1ReadersTest`.
  Затронутый feature-набор зелёный (18/18).

- **2026-05-25 — Шаг 2a / Tier 2 visibility (commit fdfd565):** `StaffVisibilityScopeService`
  переведён на Core (resolveVisibleProjectIdsByUsers / filterVisibleIdsByLocalProject /
  resolveAttachedPayload — через memberships+assignments+resolver; new accessibleLocalProjectIdsForViewer;
  конструктор +2 dep). `ProjectPointAccessService::hasProjectAccess` упрощён до **own-projects**
  (подтверждено автором — строже прежнего). `StaffVisibilityScopingTest` переписан на
  FakesCoreReadModels; контракт-тест доступа обновлён (code RUSAIFIN_{id}). 31/31 в наборе.
  ⚠ Семантика доступа изменилась: Core-членство = доступ к проекту (раньше требовался локальный пивот-линк).

## In progress
- Шаг 2b (Tier 2 — `StaffService` scope-методы: getAccessiblePointIds, resolveReportingScope/
  resolveReportingPointIds, getProjectStaff, preloadUserAttachments, getUnassignedRoleIds,
  isUserAttached-fallback). Нужен batch-by-employee для assignments (точки агента/РГ).

## Blocked
- —

## Pre-existing red (НЕ от D2, baseline на cutover-final)
- `tests/Unit/Project/CurrentProjectServiceTest` (5) — extends PHPUnit TestCase, facade `cache`
  не забутстрапен (Cache-путь добавлен в CurrentProjectService прежними коммитами).
- `tests/Unit/Staff/StaffVisibilityScopingTest` (3 из reporting-scope) — зовут несуществующий
  `bindCoreContracts()` (недописанные тесты прежнего коммита). Будут переписаны в Шаге 2.
  На HEAD группа вообще фаталила (фикс фейка в 0a поднял её до runnable).

## Next
- Шаг 2: `StaffVisibilityScopeService::resolveVisibleProjectIdsByUsers` / `filterVisibleIdsByLocalProject`
  / `resolveAttachedPayload` + `StaffService` access + `ProjectPointAccessService` — перевести
  локальные пивот-чтения на Core (через resolver). Переписать StaffVisibilityScopingTest.
- Затем Шаг 3 (Tier 4), Шаг 4 (Tier 3 reports/exports), Шаг 5 (smoke + acceptance-grep).

## Artifacts
- `cutover-status/track-d2-controllers-registry.md` (реестр читателей — этой сессии)
- rusaifin ветка `cutover-final` (от main + 2 коммита D5 `e79c2ef`,`f87a65a`); D2-коммиты появятся при реализации.
- `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 2, D2 — спека)
