---
id: F-0061
flow: sklad-pages-roles
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaisklad_back, rusaifin, rusaicore]
status: open
---

## Симптом

Полевой агент (и любая management-роль) открывает rusaisklad и получает пустой `pages` → bibli AppNavigation показывает «нет доступных страниц». Формализует и расширяет известный прод-сигнал «agent не маппится» (memory `no_available_pages_diagnosis`): дефект касается НЕ только `agent`, а ~7 ролей Core.

## Доказательства (file:line)

Цепочка `/pages`:
- `rusaisklad_back/app/Http/Controllers/API/System/PagesController.php:62-89` → `UserContextFactory::makeContext`.
- `rusaisklad_back/app/Services/User/UserContextFactory.php:54-64` — `getEffectiveRoleModel($user)`, `new UserContext($user, $effectiveRole, true)`.
- `rusaisklad_back/app/Services/Projects/CurrentProjectService.php:150` — `return $this->projectMemberships->getRole($user->id, $project->id)` (сырой Core `project_role`, без трансляции).
- `CurrentProjectService.php:153-161` — `getEffectiveRoleModel`: `Role::query()->where('code', $roleCode)->first()`; `if (!$roleCode) return null`.
- `rusaisklad_back/app/Domain/Core/Projection/CoreProjectMembershipProvider.php:38-41` — `getRole` возвращает сырой `->projectRole` из Core.
- `rusaisklad_back/app/Services/User/UserContext.php:89-97` — `getPages()`: `$role = $this->resolveRole(); if (!$role) return collect();`.

Словари ролей НЕ совпадают:
- sklad знает 4 кода: `RoleSeeder.php:17-20`, миграция `2025_02_03_000001_create_roles_and_rusaifin_user_fields.php:34-37`, enum `app/Domain/Auth/Enums/Role.php:7-10` → `{admin, manager, supervisor, promoter}`.
- rusaifin пишет в Core 11 значений `project_role`: `rusaifin/config/core.php:18-45` (`3 => ['project_role' => 'agent']` строка 24; плюс `director, account_director, support_supervisor, support_manager, project_manager, regional_director, group_leader, analyst, business_coach, client`).
- Core хранит `project_role` свободной строкой (без enum-валидации) — `rusaicore/.../StoreProjectMembershipRequest.php` (`project_role` max:64).

→ `Role::where('code','agent')->first()` = `null` → `getEffectiveRoleModel` = `null` → `getPages()` ранний `return collect()`.

## Триггер / repro

Пользователь с Core membership `project_role='agent'` (любой полевой агент после cutover) с current_project, открывает sklad → `/pages` отдаёт `pages: []`. То же для `project_manager`, `regional_director`, `support_manager`, `group_leader` и др., если у юзера нет global `role->code='admin'` (admin-shortcut `CurrentProjectService.php:146-148` спасает только локального admin).

## Корневая причина (гипотеза)

Отсутствует mapping-слой Core `project_role` (11 значений) → sklad `roles.code` (4 значения) в read-path авторизации. Симметричный маппер `CoreRoleMapper` существует в rusaifin (write-path, `config/core.php`), но обратного в sklad нет. Дефект замаскирован на BAT-приёмке: BAT-сид нормализует роли в 4-код словарь хардкодом (`RusaiskladBatSnapshotImporter` ALLOWED_MEMBERSHIP_ROLES), поэтому BAT-юзеры страницы видят, а живой rusaifin-приём (пишущий `agent`) ломается.

## Радиус поражения

Все Core-роли вне `{admin,manager,supervisor,promoter}` → пустые pages в sklad: `agent` (самый частый — полевые) + ~6 management-ролей. Симптом «нет доступных страниц» на проде.

## Направление фикса

Ввести единый маппер Core `project_role` → sklad `roles.code` в read-path (`CurrentProjectService::getEffectiveRole`/`getEffectiveRoleModel`), симметричный rusaifin `CoreRoleMapper`; либо добавить недостающие коды в `roles` + `role_pages`. Решение — за владельцем (затрагивает словарь ролей sklad).

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`CurrentProjectService:150` отдаёт сырой Core `project_role`; словарь ролей sklad — 4 кода, маппера нет → для `agent` роль null и `getPages()` пуст.
