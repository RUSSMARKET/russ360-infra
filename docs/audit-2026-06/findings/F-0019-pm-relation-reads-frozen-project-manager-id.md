---
id: F-0019
flow: project-support-membership
dimension: architecture-drift
severity: P2
confidence: likely
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Legacy-связи `User::project()` / `User::point()` для роли PROJECT_MANAGER читают замороженный `projects.project_manager_id`, который write-path больше не обновляет → новый PM не «видит» проект через эти relation, старый продолжает «видеть».

## Доказательства (file:line)
- `rusaifin/app/Models/User/User.php:145` — `hasMany(Project::class, 'project_manager_id')`; `:160-168` — `hasManyThrough(... 'project_manager_id')` для PM-ветки.
- Контраст: РД-ветка `:170-174` уже переключена на Core (`regionalDirectorLocalProjectIds()`), agent — `agentLocalPointIds()`.
- `ProjectService::setProjectManager()` пишет PM только в Core; `projects.project_manager_id` заморожен (D5).

## Триггер / repro
Любой код, читающий `$pmUser->project` / `$pmUser->point` (Eloquent relation, не visibility-service), вернёт проекты по старому `project_manager_id`, который не обновляется при назначении нового PM.

## Корневая причина (гипотеза)
Незавершённый reader-switch для PM-ветки `project()/point()` (D2-residue). Visibility-scope (основной путь) уже на Core и корректен, поэтому радиус ограничен прямыми обращениями к relation.

## Радиус поражения
Любой оставшийся прямой читатель `User::project()/point()` для PM-роли (экспорты/листинги).

## Направление фикса (1-2 строки, НЕ реализовано)
Перевести PM-ветку на `ProjectMembershipProvider` (по аналогии с `regionalDirectorLocalProjectIds`), либо подтвердить отсутствие live-читателей и удалить ветку.
