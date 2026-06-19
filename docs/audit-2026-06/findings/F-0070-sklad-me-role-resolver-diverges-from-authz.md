---
id: F-0070
flow: user-profile-me
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом

`/api/v1/auth/me` проецирует `role` через резолвер, который при отсутствии выбранного проекта приоритизирует ГЛОБАЛЬНУЮ `users.role_id`, тогда как authz эндпоинтов/`/pages` берёт роль СТРОГО из membership текущего проекта (иначе `null`). Во состоянии «несколько проектов, ни один не выбран» `/me` отдаёт непустую глобальную роль, а реальный authz не даёт ничего → фронт показывает роль, которой юзер по факту не обладает.

## Доказательства (file:line)

- `/me`-резолвер: `rusaisklad_back/app/Services/User/UserReadService.php:352-368` (`roleCodeForUser`): при `projectId === null` (нет current_project) пропускает Core `getRole` и возвращает глобальную `$user->role->code` (строки 361-362), затем локальный membership-fallback (365-367).
- `buildMePayload` зовёт `roleCodeForUser($user, $currentProjectId)` (`:186`), `$currentProjectId` = `null` при >1 проекте без выбранного.
- authz-резолвер (другой): `app/Services/User/UserContextFactory.php:60-61` → `app/Services/Projects/CurrentProjectService.php:139-151` (`getEffectiveRole`) — роль только из membership current_project (+admin override), без global-fallback; нет проекта → `null`.
- pages/permissions используют authz-резолвер: `PagesController.php` (getPages), `CheckPermission` middleware.

## Триггер / repro

Юзер с >1 доступными проектами без выбранного (`current_project_id` пуст) и непустым `users.role_id` (напр. legacy `manager`): `/me` → `role: "manager"` + `project_selection_required: true`. Эндпоинты под `CheckPermission`/`/pages` → 409 PROJECT_SELECTION_REQUIRED или пустые pages. Фронт инициализирует UI по роли из `/me`, реальные запросы отвергаются. (Когда проект выбран — `roleCodeForUser` идёт в Core и согласован с authz.)

## Корневая причина (гипотеза)

Три параллельных резолвера роли с разной приоритизацией: `/me` (роль-проекция, global-first при null), authz (`getEffectiveRole`, membership-only), legacy-fallback (`getRoleCode`, см. F-0071). Не унифицированы. Бьёт в unselected-multi-project bootstrap-состоянии (отсюда P2, не P1: сопровождается флагом `project_selection_required`).

## Радиус поражения

sklad-юзеры с непустым `users.role_id` и множественными/невыбранными проектами; в частности cold-start без выбранного проекта.

## Направление фикса

`/me`-проекция роли должна использовать тот же резолвер, что authz (`CurrentProjectService::getEffectiveRole`), а не `roleCodeForUser` с приоритетом глобальной роли; при `project_selection_required` отдавать `role: null`. Связано с F-0062, F-0063, F-0071.
