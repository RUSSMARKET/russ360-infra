---
id: F-0105
flow: rusaifin-inventory-agent
dimension: data-integrity
severity: P3
confidence: needs-verification
services: [rusaifin]
status: open
---

## Симптом
`weekly_inventories`/`supply_requests` ссылаются на `point_id`/`project_id` без видимого каскада/обнуления; при удалении точки/проекта заявки осиротеют, а scope-проверка сверяет именно по `project_id`/`point_id`.

## Доказательства (file:line)
- `rusaifin/app/Models/Inventory/WeeklyInventory.php:37-45` — `belongsTo(Point)`/`belongsTo(Project)` без soft-delete каскада.
- `rusaifin/app/Services/Inventory/InventoryAccessService.php:180-216` (`assertCanViewWeekly`) — скоуп по `project_id`/`point_id`.
- НЕ верифицировано: FK `onDelete` на `weekly_inventories`/`supply_requests`/`weekly_inventory_items` (миграции не читались).

## Триггер / repro
Удалить/деактивировать точку с заявками → заявка с битым `point_id`, выпадает из scope-проверок.

## Корневая причина (гипотеза)
Класс F-0002 (orphan). Требует сверки FK-констрейнтов в миграциях.

## Радиус поражения
Заявки агентской инвентаризации при удалении точки/проекта.

## Направление фикса
Проверить FK `onDelete` в миграциях; при отсутствии каскада — добавить или гасить заявки при удалении точки.
