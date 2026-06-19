---
id: F-0082
flow: shift-planning
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Write-эндпоинты плановых смен (`POST /planned-shifts/batch`, `PUT /planned-shifts/{id}`, `DELETE /planned-shifts/batch`) не проверяют, что целевой `user_id`/смена входят в зону видимости вызывающего. Любой носитель права `staff.management` (РГ/РП/саппорт/админ) может создать/переназначить/удалить плановую смену ЛЮБОМУ агенту системы, в т.ч. чужого проекта.

## Доказательства (file:line)
- `rusaifin/routes/api.php:146` — группа `planned-shifts` гейтится только `CheckPermission:staff.management` (роль-уровень, без object-scope).
- `rusaifin/app/Http/Requests/PlannedShifts/BatchStorePlannedShiftRequest.php:12-16` — `authorize(): bool { return true; }` с `// TODO: Добавить проверку прав`.
- `…/BatchStorePlannedShiftRequest.php:87` — `planned_shifts.*.user_id => required|exists:users,id` (только существование).
- `rusaifin/app/Http/Controllers/User/PlannedShiftController.php:798-806` — `batchStore` берёт `user_id` из тела и `PlannedShift::create(...)` без проверки против `StaffVisibilityScopeService::resolveVisibleUserIds`.
- `…/PlannedShiftController.php` `update` — меняет `user_id`/время route-bound `$plannedShift` без проверки, что viewer видит и старого, и нового агента; `UpdatePlannedShiftRequest::authorize()` тоже `true`. Для GROUP_LEADER `update` к тому же не проверяет `created_by_user_id === authUser->id`, хотя `batchDestroy` для GL такую own-проверку имеет (асимметрия).
- `batchDestroy` — own-check есть только для GL, для РП/РГ/саппорта удаляет любую смену по id.

## Триггер / repro
РГ проекта A: `POST /api/planned-shifts/batch {planned_shifts:[{user_id:<агент проекта B>, ...}]}` → 201, смена создана чужому агенту. Аналогично `PUT /api/planned-shifts/{любой id}` с подменой `user_id`, и `DELETE /batch` чужих смен.

## Корневая причина (гипотеза)
Авторизация ограничена ролевым `CheckPermission`, object-level scope-check намеренно отложен (`TODO`, `authorize()=true`). Снижено с P1 (так оценил субагент) до P2: актор — доверенный внутренний staff с management-правом (не внешний), нет privilege escalation, scope = данные графиков, фронт обычно скоупит список агентов. Кандидат на повышение в фазе 2 (явно недоделанная authz). Связано с F-0052 (видимость агентов РГ/РП).

## Радиус поражения
Все 3 write-эндпоинта планов; целостность графиков между проектами; возможность саботажа расписаний чужих агентов любым staff.management-актором.

## Направление фикса
В контроллере валидировать каждый `user_id` (и route-bound `$plannedShift->user_id`, старый+новый в `update`) против `StaffVisibilityScopeService::resolveVisibleUserIds($viewer)`; для непривилегированных — 403 при выходе за scope; в `update` добавить GL own-check как в `batchDestroy`; распространить ownership/scope-check на не-GL роли в `batchDestroy`.
