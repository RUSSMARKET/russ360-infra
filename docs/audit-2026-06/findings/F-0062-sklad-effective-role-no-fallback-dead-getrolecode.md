---
id: F-0062
flow: sklad-pages-roles
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом

Для `/pages` роль резолвится строго из Core membership текущего проекта. Если Core не вернул роль для current_project, юзер сразу получает пустые pages — даже если у него есть global `role` или membership в другом проекте, которые `User::getRoleCode()` отдал бы как fallback. «Умный» fallback в `UserContext` написан, но мёртв.

## Доказательства (file:line)

- `rusaisklad_back/app/Services/Projects/CurrentProjectService.php:139-151` — `getEffectiveRole`: при `getRole()===null` возвращает `null`, без обращения к `$user->role?->code` или другому membership.
- `CurrentProjectService.php:153-161` — `getEffectiveRoleModel`: `if (!$roleCode) return null`.
- `rusaisklad_back/app/Services/User/UserContextFactory.php:54-64` — всегда строит `new UserContext($user, $effectiveRole, true)` (hasExplicitRole=**true**).
- `rusaisklad_back/app/Services/User/UserContext.php:225-253` — `resolveRole`: при `hasExplicitRole` (строки 227-228) возвращает `effectiveRole` СРАЗУ, не доходя до fallback-ветки `getRoleCode()` (строки 245-252). Т.е. fallback `User::getRoleCode()` (`User.php` ~99-105: global role → first membership → 'promoter') для `/pages` никогда не выполняется.

## Триггер / repro

Юзер с global `role` локально (например admin-проекция), но без Core membership в current_project (или current_project не выбран корректно): `getEffectiveRole` → `null` (если не сработал admin-shortcut на `CurrentProjectService.php:146`) → пустые pages, хотя `getRoleCode()` дал бы роль.

## Корневая причина (гипотеза)

Два независимых пути резолва роли с разной семантикой fallback: `getEffectiveRole` (membership-only, fail-to-null) и `User::getRoleCode` (многоуровневый fallback). `UserContextFactory` форсит `hasExplicitRole=true`, шунтируя fallback-ветку в `UserContext::resolveRole`.

## Радиус поражения

Юзеры с global-ролью, но без Core membership в текущем проекте; зависит от консистентности данных Core↔локаль. Latent, но реалистичен после переводов/рассинхрона membership.

## Направление фикса

Выровнять `getEffectiveRole` fallback с `getRoleCode` (global role → первый membership), либо явно зафиксировать «pages зависят ТОЛЬКО от membership current_project» и удалить мёртвую fallback-ветку `UserContext::resolveRole:245-252`. Связано с F-0061 (общий read-path резолва роли).
