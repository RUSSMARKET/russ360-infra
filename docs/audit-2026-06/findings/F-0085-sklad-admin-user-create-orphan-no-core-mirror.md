---
id: F-0085
flow: sklad-projects-admin
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaisklad_back, rusaicore]
status: open
---

## Симптом
`POST /admin/users` в rusaisklad_back создаёт локального `User` чисто в БД sklad — без Core employee/membership-зеркала и без back-sync в Core. Это единственный незакрытый stage1-guard'ом write-путь sklad: проекты и memberships прикрыты `disable_local_*_writes` (default true), а user/employee-writes guard'а НЕ имеют (флага `disable_local_user_writes` не существует).

## Доказательства (file:line)
- `rusaisklad_back/app/Http/Controllers/API/Users/UserController.php:376-392` — `store()`: только `canManageUsers` + `managementService->create($validated)`; нет `guardLocal*`, нет Core-вызова.
- `rusaisklad_back/app/Services/User/UserManagementService.php:20-37` — `create()` = `User::create($data)`, конец. Никакого Core.
- `rusaisklad_back/app/Domain/Core/Sync/CoreEmployeeShadowSyncService.php` — синк направлен ТОЛЬКО Core→sklad (fetch из Core → `createLocalAnchor`/update локально); локально-созданный юзер в Core не пушится.
- `rusaisklad_back/config/core.php` — есть `disable_local_project_writes` / `disable_local_membership_writes` (default true), но НЕТ `disable_local_user_writes`; `store` ничем не прикрыт.

## Триггер / repro
Admin/manager вызывает `POST /admin/users` → создаётся local user без `external_user_id` → он orphan: не резолвится `LocalExternalIdMap::userExternalId()` (null), не попадает в Core-backed reads (`CoreProjectMembershipProvider`, employee directory). Усугубление: привязать его к проекту локально нельзя — membership-write закрыт guard'ом (default 403). Юзер остаётся невидимым и непривязываемым.

## Корневая причина (гипотеза)
После Track D3/D4 sklad стал read-only по employees/projects/memberships (source of truth = Core), но legacy admin user-CRUD остался и пишет локально без согласования с Core; stage1-guard suite не покрывает user-writes. Класс F-0002 (orphan без Core-зеркала), отдельная точка входа в rusaisklad_back (родственно memory `stage2_orphan_users_recurring_regression`, но та про rusaifin). Снижено до P2: вторичный legacy-путь, основной hire-flow — rusaifin.

## Радиус поражения
Любой пользователь, заведённый через sklad-admin после cutover: orphan, невидим Core-backed чтениям, непривязываем к проектам.

## Направление фикса
Добавить `guardLocalUserWrites` (как для проектов/memberships) — запретить локальное создание, source of truth = Core; либо при создании синхронно заводить Core employee через gateway и записывать `external_user_id` обратно.
