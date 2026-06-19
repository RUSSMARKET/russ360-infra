---
id: F-0013
flow: project-support-membership
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Назначение второй проектной роли тому же сотруднику на том же проекте ТИХО перезаписывает его прежнюю открытую membership (роль A → роль B), без следов. Хуже: после подмены снятие исходной роли A (`deleteSupport`/`deleteRegionalDirector`) не срабатывает — роль «прилипает».

## Доказательства (file:line)
- `rusaifin/app/Services/Project/ProjectService.php:352-361` — `findOpenMembershipOnProject()` ищет открытую membership по `employeeExternalId` БЕЗ фильтра по роли.
- `:320-328` — `coreMembershipCreate()` при найденной open-записи вызывает `ensureOpenMembershipRole()`.
- `:363-378` — `ensureOpenMembershipRole()` делает `update(projectRole: <новая>)` — перезаписывает `project_role` существующей записи. Комментарий `:364`: «Rusaicore allows one open membership per (employee, project) regardless of role».
- `:380-388` — `coreMembershipEnd()` ищет membership через `openMemberships($projectRole)` (фильтр строго по роли, `:300-303`); после свопа роли запись имеет другую роль → `null` → no-op (роль не закрывается).
- rusaicore `CreateProjectMembership` — инвариант «одна открытая membership на (employee, project)» (`whereNull('ended_at')->exists()` → `ConflictException::openProjectMembershipExists`).

## Триггер / repro
Сотрудник имеет открытую membership на проекте в роли A (напр. support_manager). Назначение того же человека ролью B (PM/РД/support) на том же проекте → роль A молча становится B. Последующее «снять роль A» не закрывает membership.

## Корневая причина (гипотеза)
Доменный конфликт: Core допускает 1 open membership на (employee, project), а домен rusaifin потенциально допускает несколько ролей одного человека на проекте; обход через role-swap ломает идемпотентность ролей и снятие.

## Радиус поражения
Владелец подтвердил (2026-06-09): доменно **одна роль на проект у человека** → сценарий одновременной порчи двух ролей не реализуется, поэтому severity = **P1** (не P0). Остаётся живой риск асимметрии при СМЕНЕ/СНЯТИИ роли: после role-swap вызов снятия по старой роли (`deleteSupport`/`deleteRegionalDirector`) — no-op («прилипшая» роль), т.к. `coreMembershipEnd` ищет строго по прежней роли.

## Направление фикса (1-2 строки, НЕ реализовано)
Согласовать доменное правило «сколько ролей на проекте у одного человека». Либо в Core ввести уникальность по (employee, project, project_role) и убрать role-swap; либо в rusaifin фильтровать `findOpenMembershipOnProject` по роли.
