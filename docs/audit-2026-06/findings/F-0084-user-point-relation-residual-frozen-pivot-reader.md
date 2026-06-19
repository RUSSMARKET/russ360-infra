---
id: F-0084
flow: shift-planning
dimension: architecture-drift
severity: P3
confidence: likely
services: [rusaifin]
status: open
---

## Симптом
Eloquent-связь `User::point()` всё ещё читает замороженные post-cutover pivot'ы (`project_point_agents` для агента, `group_leader_id` для РГ, `project_manager_id` для РП). Любой потребитель, использующий `$user->point` / `whereHas('point')` напрямую (не переключённый Core-метод), получает устаревший набор точек → у агентов, привязанных ТОЛЬКО через Core после cutover, точки пусты. Конкретно проявляется в `getStaffResult` (флаг `is_transferred`).

## Доказательства (file:line)
- `rusaifin/app/Models/User/User.php:180` — default-ветка (agent): `belongsToMany(Point::class, 'project_point_agents', 'agent_id', 'point_id')` (frozen pivot).
- `…/User.php:177` — GROUP_LEADER: `hasOne(Point::class, 'group_leader_id')` (frozen).
- `…/User.php:160-168` — PROJECT_MANAGER: `hasManyThrough` по `project_manager_id` (frozen, = F-0019).
- `…/User.php:184-189` — docblock прямо фиксирует, что `point()` намеренно остаётся frozen-relation (нужен для `whereHas('point')` в листингах/экспортах), а Core-резолв вынесен в отдельный метод → не-переключённые консьюмеры читают frozen.
- `rusaifin/app/Http/Controllers/Staff/PlansController.php` `getStaffResult` (≈:889-926) — `with('point:id')` + расчёт `is_transferred` через `$agent->point`.

## Триггер / repro
Агент привязан к точке только через Core assignment после cutover (legacy `project_point_agents` пуст) → `$agent->point` пуст → в `/api/staff/result` `is_transferred` вычисляется неверно. Шире: любой листинг/экспорт с `whereHas('point')` может не показывать post-cutover-привязанных агентов.

## Корневая причина (гипотеза)
Reader-switch 2026-05-29 (memory `frozen_pivot_reader_switch_2026-05-29`) перевёл основные shift/plan/export-пути на Core-метод, но сама relation `point()` оставлена frozen-backed для совместимости; оставшиеся прямые консьюмеры `point`/`whereHas('point')` не мигрированы. Новый инстанс класса F-0019/F-0071.

## Радиус поражения
Подтверждённый конкретный — индикатор `is_transferred` в отчёте (display, не доступ) → P3. Потенциально шире (все консьюмеры `point()`/`whereHas('point')`) — требует отдельного sweep'а в фазе 2.

## Направление фикса
Провести инвентаризацию консьюмеров `User::point()`/`whereHas('point')`; перевести их на Core-резолв (`StaffVisibilityScopeService::pointIdsByUser`); для `getStaffResult` резолвить точки агента через Core вместо `$agent->point`. См. F-0019, F-0071.
