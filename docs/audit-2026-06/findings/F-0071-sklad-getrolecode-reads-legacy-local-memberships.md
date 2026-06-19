---
id: F-0071
flow: user-profile-me
dimension: architecture-drift
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом

`User::getRoleCode` резолвит membership-роль из ЛОКАЛЬНОЙ Eloquent-таблицы `memberships` (frozen/legacy pivot), а не из Core-контракта. Этот резолвер ЖИВ через `UserResource` → проекции роли пользователя в списках/ресурсах берутся из legacy-pivot вместо Core, расходясь с post-cutover Core-данными.

## Доказательства (file:line)

- `rusaisklad_back/app/Models/User.php:83-105` (`getRoleCode`) — строки 86, 93, 103 дёргают `$this->memberships()` (локальная HasMany).
- `app/Models/User.php` — `memberships()` → `Membership` (локальная таблица `memberships`); `projects()` = `belongsToMany(..., 'memberships')->withPivot('role')`.
- ЖИВОЙ caller: `app/Http/Resources/API/Users/UserResource.php:25-26` — `getRoleCode($project->id)` / `getRoleCode()`.
- Также вызывается из мёртвого authz-fallback `app/Services/User/UserContext.php:247` (`resolveRole`), который не достигается через factory (см. F-0062).
- Контраст: канонический Core-путь — `CurrentProjectService` через `ProjectMembershipProvider` (Core gateway, `:27,150`).

## Триггер / repro

Любой эндпоинт, сериализующий `UserResource` (списки пользователей/участников), показывает роль из локального pivot. Если локальная `memberships` расходится с Core (Core-изменения без зеркалирования в локаль; shadow-sync для sklad частично off) — отображается stale-роль.

## Корневая причина (гипотеза)

Остаточный legacy-резолвер на локальном `memberships`-pivot не выпилен после reader-switch на Core. Магнитуда расхождения зависит от свежести shadow-sync локальной таблицы.

## Радиус поражения

Проекции роли через `UserResource` (списки/детали пользователей). Не authz-решение happy-path (authz идёт через Core `getEffectiveRole`), а display-drift — отсюда P2, не P1.

## Направление фикса

Свести `UserResource` и fallback `UserContext::resolveRole` к Core-резолверу (`getEffectiveRoleModel`/`getEffectiveRole`); пометить локальную `memberships`-relation как deprecated для authz/проекций. Связано с F-0062.
