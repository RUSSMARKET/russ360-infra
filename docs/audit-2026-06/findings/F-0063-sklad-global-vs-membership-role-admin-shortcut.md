---
id: F-0063
flow: sklad-pages-roles
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом

Один юзер может резолвиться как «admin» на одном authz-пути и как другая/пустая роль на другом: `/pages` и `UserContext` берут роль из Core membership, тогда как `isSystemAdmin`/admin-shortcut берут global `$user->role?->code`. Конкретизирует известный класс (audit 2026-05-18, строка 141 — смешивание global vs membership уровней), но с новыми точными file:line в read-path pages.

## Доказательства (file:line)

- `rusaisklad_back/app/Services/Projects/CurrentProjectService.php:146-148` — `getEffectiveRole`: admin-shortcut `if ($this->isSystemAdmin($user)) return 'admin';` (по global роли) ДО чтения membership.
- `CurrentProjectService.php:169-172` — `isSystemAdmin`: `$user->role?->code === 'admin'` (global `users.role_id`-проекция, отдельный источник от Core `project_role`).
- `rusaisklad_back/app/Services/User/UserContext.php:83-87` (`isAdmin`) и `:89-97` (`getPages`) — резолвят через `resolveRole`→effectiveRole (membership-derived).

## Триггер / repro

Юзер с global `users.role_id`, маппящимся в локальный `role.code='admin'`, но с Core `project_role` ≠ admin в current_project: на `/pages` сработает admin-shortcut (`:146`) → admin-страницы, независимо от реальной Core-роли в проекте. Обратно: юзер с Core `project_role='admin'`, но без локального global-admin — shortcut не сработает, роль возьмётся из membership. Несогласованность двух источников истины.

## Корневая причина (гипотеза)

Два конкурирующих источника роли для sklad-авторизации: rusaifin global `role_id`-проекция в `users.role_id` (локальная) и Core `project_role` (membership). Нет единого arbiter; admin-shortcut доверяет локальному global-полю.

## Радиус поражения

Authz-чувствительные пути sklad: потенциально admin-страницы по локальному global-полю в обход Core-membership роли проекта (видимость не той роли), либо отказ. Краевой — зависит от того, насколько `users.role_id`-проекция расходится с Core.

## Направление фикса

Зафиксировать single source of truth для sklad-авторизации (membership-роль current_project) и свести global admin-shortcut к нему, либо явно задокументировать инвариант. Затрагивает контракт guard'а — обсудить с владельцем. Связано с F-0061, F-0062.
