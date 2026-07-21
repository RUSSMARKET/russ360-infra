---
id: F-0052
flow: staff-visibility
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
REGIONAL_DIRECTOR и PROJECT_MANAGER при запросе дерева персонала проекта (`getStaffProject` → `StaffService::getProjectStaff()`) видят на каждой точке ПУСТОЙ список агентов, хотя агенты на точках их проектов есть.

## Доказательства (file:line)
- `app/Services/Staff/StaffVisibilityScopeService.php:45-54` — `isPrivilegedViewer` = ADMIN/DIRECTOR/ACCOUNT_DIRECTOR/SUPPORT_SUPERVISOR/ANALYST. RD и PM туда НЕ входят.
- `app/Services/Staff/StaffService.php:539-558` — привилегированные идут в ветку `$visibleAgentUserIds = null` (`:541`); RD/PM (не привилегированные, не SUPPORT_MANAGER) получают `resolveVisibleUserIds(...)` (`:552-557`).
- `app/Services/Staff/StaffVisibilityScopeService.php:125-166` — `computeVisibleUserIds` строит набор ТОЛЬКО из `projectMembershipProvider->listForProjectExternalIds(...)` (`:151`) + сам viewer. Агенты живут в `operational_location_assignments` (role=agent), НЕ в `project_memberships` → в набор не попадают.
- `app/Services/Staff/ProjectStaffReader.php:101-105` — при `is_array($visibleAgentUserIds)` агенты точки фильтруются `whereIn('id', $visibleAgentUserIds)` → пусто для RD/PM.
- Дев-комментарий `StaffService.php:550-551` сам признаёт: «resolveVisibleUserIds для саппорта вернул бы только membership-users (без агентов)» — поэтому для SUPPORT_MANAGER carve-out `null` сделан, а для RD/PM нет.

## Триггер / repro
Залогиниться РГ или РП, открыть дерево персонала проекта (`getStaffProject`). На точках проекта агентов нет, хотя они назначены в Core.

## Корневая причина (гипотеза)
`visibleAgentUserIds` для RD/PM формируется из членств (membership-only набор), а агенты в Core живут в assignments. Carve-out `null` (без agent-фильтра) сделан только для SUPPORT_MANAGER.

## Радиус поражения
Дерево персонала (`getStaffProject`/`getProjectStaff`) для всех RD и PM: списки агентов на точках пусты. Базовая операционная видимость роли сломана.

## Направление фикса (1-2 строки, НЕ реализовано)
Распространить ветку `null` (без agent-фильтра) на RD/PM как для SUPPORT_MANAGER, либо добавлять в `visibleAgentUserIds` агентов точек доступных проектов (`memberUserIdsForLocalPointIds(..., ['agent'])`).

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`isPrivilegedViewer` всё те же 5 ролей без РД и PM; `computeVisibleUserIds` строится только из membership-провайдера, без агентских assignments.
