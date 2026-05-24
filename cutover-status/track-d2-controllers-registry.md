# Track D2 — Реестр читателей legacy-домена в rusaifin

**Артефакт Track D2.** Построен 2026-05-24 grep'ом + построчным аудитом (3 параллельных разведки).
Дополняет `track-d2-rusaifin-readers.md` (status). Source of truth по тому, *что* переключаем.

## 0. Что считается legacy-доменом

| Объект | Локальное представление | Core-эквивалент (authoritative после cutover) |
|---|---|---|
| Проект | `App\Models\Project\Project` (`projects`) | `projects` (ProjectCatalog / ProjectView) |
| Точка | `App\Models\Project\Point` (`project_points`) | `operational_locations` (OperationalLocationCatalog / OperationalLocationView) |
| Агент↔точка | пивот `project_point_agents` (`Point::agents()`) | `operational_location_assignments` (role=agent) |
| РГ (лидер)↔точка | FK `project_points.group_leader_id` (`Point::leader()`) | `operational_location_assignments` (role=group_leader) |
| Саппорт↔проект | пивот `project_supports` (`Project::supports()`) | `project_memberships` (role=support) |
| РД↔проект | пивот `project_regional_directors` (`Project::regional_directors()`) | `project_memberships` (role=regional_director) |
| ПМ↔проект | FK `projects.project_manager_id` (`Project::project_manager()`) | `project_memberships` (role=project_manager) |

## 0a. Мосты Core ↔ local (КЛЮЧЕВОЕ)

ReadModel'и Core несут `id` = **Core-овский** int id, НЕ локальный rusaifin id. Чтобы
переключённый код смог джойнить локальные `shifts` / `shift_reports` / `product_history` /
`point_products`, нужен перевод Core-external_id → local int id:

| Перевод | Через что |
|---|---|
| Core location externalId → local `project_points.id` | колонка `project_points.core_location_external_id` (миграция 2026_05_15) |
| Core employee externalId → local `users.id` | колонка `users.core_employee_external_id` (миграция 2026_04_16) |
| Core project ↔ local `projects.id` | code-конвенция `RUSAIFIN_{local_id}` (см. `SeedProdMirror…:292`, `CurrentProjectService:195`) — **на `projects` нет колонки external_id** |

`project_points` / `projects` остаются **читаемыми** (D5 морозит write, не дропает) — они
FK-якорь для shifts/reports/products. Перевод external_id↔local_id — отдельный
**`CoreScopeResolver`** (новый сервис), он же — единственный санкционированный residue
по acceptance-grep'у (см. status §Acceptance).

## 0b. Данные, которых НЕТ в Core (читаются локально, остаются как есть)

- **products**: `point_products`, `projects_products`, `Project::products()`, `Point::products()` — товарная матрица живёт только в rusaifin.
- **`project_points.referal`**: referal-код точки (регистрация агентов) — нет в Core OL.
- **shift / report домен**: `shifts`, `shift_reports`, `shift_report_fields`, `product_history`, `ProductConsentSession` — целиком локальные.

Эти чтения `Point::`/`Project::` **остаются** и будут матчиться acceptance-grep'ом —
ожидаемый residue, не нарушение (см. status §Acceptance — уточнённый список).

---

## 1. Tier 0 — уже на Core (работы нет)

| Файл | Метод | Статус |
|---|---|---|
| `Services/Project/CurrentProjectService.php` | весь (read через ProjectCatalog + ProjectMembershipProvider; write только локальное поле `users.current_project_external_id`) | ✅ Core |
| `Services/Project/ProjectBootstrapPayloadFactory.php` | `make()` | ✅ Core |

## 2. Tier 1 — чистые catalog/membership reads, прямой swap (низкий риск)

| Файл | Метод → route | Legacy read (строки) | Целевой gateway |
|---|---|---|---|
| `Http/Controllers/Project/ProjectController.php` | `getProject()` → `GET /api/project/{id}` | 110–121 `Project::where()->with(project_manager, regional_directors, supports)` | ProjectCatalog::findByExternalId + memberships(project) → роли PM/RD/support |
| `Http/Controllers/Project/PointController.php` | `getPointAgents()` → `GET /api/point/{id}/agent` | 451 `Point::with(agents)` | OperationalLocationAssignmentProvider (role=agent) + EmployeeDirectory для ФИО |
| `Http/Controllers/User/UserController.php` | `getUser()` → `GET /api/user` | 58–60 `Point::where(group_leader_id)` | assignments(employee, role=group_leader) → точка РГ |

⚠ `getProjectProducts()` (ProjectController 749) и `getPointAgents` в части products — **products
не в Core** → остаются локальными.

## 3. Tier 2 — visibility scope (горячее, критично по latency)

| Файл | Метод | Legacy read (строки) | Примечание |
|---|---|---|---|
| `Services/Staff/StaffVisibilityScopeService.php` | `resolveVisibleUserIds()` (кэш 30s) | 161 `Point::where(group_leader_id)`, 165–167 `Point::whereHas(agents)` | основной путь видимости; уже частично Core-aware (`core_employee_external_id`) |
| ↑ | `resolveVisibleProjectIdsByUsers()` | 186–222 — 4 EXISTS по `project_supports`/`project_regional_directors`/`project_points`+`project_point_agents` | обратный lookup users→projects |
| ↑ | `filterVisibleIdsByLocalProject()` | 239–251 `whereHas(project/point)` + `project_supports` | |
| `Services/Staff/StaffService.php` | `getAccessiblePointIds()` | 585–591 `whereIn(group_leader_id)` + EXISTS `project_point_agents` | |
| ↑ | `getProjectStaff()` | 471–556 `Project::with(regional_directors, project_manager, supports, points.agents, points.leader)` | 3+ уровня with(); тяжёлое |
| ↑ | `preloadUserAttachments()` | 730–772 `DB::table()` по 5 пивотам | батч-проверка привязок |
| ↑ | `isUserAttached()` (fallback) | 823–843 `Project::whereHas(points.agents/regional_directors/supports)` | |
| ↑ | `getUnassignedRoleIds()` | 65–81 pluck из `projects`/`project_regional_directors`/`project_points`/`project_point_agents` | |
| `Services/Project/ProjectPointAccessService.php` | `hasProjectAccess()` / `hasPointAccess()` | 23 `Project::find`, 53 `Point::find`, 58 `project_id` | + `current_project_external_id` |

## 4. Tier 3 — reports / exports (самое тяжёлое; scope-resolve через Core, JOIN локально)

Паттерн для всех: (1) резолвим scope (agent_ids / point_ids / project_ids) через Core
memberships+assignments + `CoreScopeResolver` перевод в local ids; (2) JOIN локальных
`shifts`/`shift_reports`/`product_history` как сейчас (эти данные не в Core).

| Файл | Метод | Legacy read (строки) | Объём (риск) |
|---|---|---|---|
| `Services/Reporting/StaffEffectivenessMetricsService.php` | `getShiftReportProductsForProject` / `buildMetricsMapForProject` / `buildFactRows` | 35 `Project::with(relations)`, 192–202 `points.products.shiftReportFields`, 213–347 тяжёлые JOIN | 10K–100K строк |
| `Http/Controllers/Staff/PlansController.php` | `getShiftReportFieldsByProjects()` → `GET /api/shift/reports/fields/by-projects` | 403–442 `Project::with(points.products…)`, `Point::whereIn->pluck(project_id)` | средне |
| ↑ | `getStaffResult()` → `GET /api/staff/result` | 708–714 `Point::whereNotNull(group_leader_id)`, 747–748, 856–904 `group_leader_id` WHERE | высоко |
| ↑ | `exportStaffRegistry()` → `GET /api/staff/registry/export` | 1451 `Point::where->value(project_id)` | |
| `Exports/MagnitTotalResultExport.php` | `view()` | 89 `Point::where(project_id)`, 101–121 `Project::whereHas(points)`, 138–150 `Shift::with(point.project)`, 315 `Project::whereIn` | ОЧЕНЬ высоко |
| `Exports/StaffEffectivenessExport.php` | `view()` | 97–117 ShiftReport JOIN ×3, 139–172 point/shift lookup | ОЧЕНЬ высоко |
| `Exports/TotalResultExport.php` | `view()` | 52–83 `Project::with(points.agents, points.leader)`, 99–112 ShiftReport JOIN | ОЧЕНЬ высоко |

## 5. Tier 4 — инцидентные reads

| Файл | Метод | Legacy read (строки) | Целевой gateway |
|---|---|---|---|
| `Services/User/UserService.php` | `getProducts()` | 313–357 `Project::whereHas(points/regional_directors)` / `project_manager_id` | memberships+assignments scope → products локально |
| ↑ | `getAgentsId()` | 888–932 `whereHas(point.project.supports/regional_directors)` | memberships+assignments |
| ↑ | `isAttached()` (782–789) + `isAttachedLegacy()` (795–829) | Core-first уже есть; legacy-fallback убрать после переключения | |
| `Services/Products/ProductService.php` | `projectHasAccess()` | 258–278 `Project::where(project_manager_id)` / `whereHas(regional_directors)` / `Point::where(group_leader_id)` / `whereHas(agents)` | memberships+assignments |
| `Services/System/NotificationService.php` | `NewUser()` / `UserBlocked()` | 90–92, 128–130 `Project::with(points, supports:id)` | memberships(role=support) |
| `Http/Controllers/Staff/StaffRegistrationController.php` | `sendAccessGrantedEmail()` / `getRegistrationUser()` / `attachReferalPoints()` | 43 `Project::value(name)`, 48–51/227–272 `Point` по `referal` | ⚠ `referal` локальный → остаётся local catalog read; имена — из Core ok |
| `Http/Controllers/Internal/Registration/RegistrationInternalController.php` | `init()` | 62 `Point::where(referal)` | ⚠ referal → локально |

## 6. WRITE-сайты — НЕ трогаем (D4)

Зафиксированы для контекста, чтобы reader-switch их случайно не задел:

- `PointService`: `create`/`delete`/`setGroupLeader`/`addAgent`/`deleteAgent`/`addProduct`/`deleteProduct` (уже dual-write в Core с 2026-05-18).
- `ProjectService`: `setProjectManager`/`add|delete|setRegionalDirector(s)`/`add|deleteSupport`/`add|deleteProduct`.
- `ProjectController`: `createProject`/`updateProject`/`deleteProject`/`setProjectSupport`/`activate|deactivateProject`/`add|deleteProjectProduct`.
- `SystemController`: `addProductToPoints`/`detachProductFromPoints`/`syncProjectProductsToPoints`.
- `UserService::detachFromProjectsAndPoints()` (массовый DELETE из пивотов + обнуление FK).

Многие D4-методы СНАЧАЛА читают legacy (`Point::find`, `Project::find` для истории/валидации) —
эти точечные read-перед-write оставляем D4 (они исчезнут вместе с write-свитчем).

## 7. Связанные тесты (переписать через mock Core)

- `tests/Feature/ProjectPointAccessHttpContractTest.php` — уже на mock-паттерне (`bindCoreContracts()`+`setCoreState()`).
- `tests/Feature/StaffListVisibilityTest.php` — уже на mock-паттерне.
- `tests/Feature/ProjectContextHttpContractTest.php`
- `tests/Unit/Project/CurrentProjectServiceTest.php`, `ProjectBootstrapPayloadFactoryTest.php`, `tests/Unit/Staff/StaffVisibilityScopingTest.php`
- Новые: на каждый переключённый Tier 1/2/3 метод.
