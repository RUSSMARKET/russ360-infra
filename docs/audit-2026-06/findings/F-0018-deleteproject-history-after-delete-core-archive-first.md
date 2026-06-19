---
id: F-0018
flow: project-support-membership
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
`deleteProject`: Core помечает проект `archived` ДО локального удаления; при сбое локального delete проект остаётся активным anchor в rusaifin при archived-статусе в Core (рассинхрон). Плюс History пишется уже по удалённой модели.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Project/ProjectController.php:468-479` — порядок: Core `update(status:archived)` → `$project->delete()` → `History::Create` с `$project->name`/`$project->id` (после `delete()`).

## Триггер / repro
Сбой MySQL-delete после успешного Core-archive → проект «archived» в Core, активный anchor в rusaifin.

## Корневая причина (гипотеза)
Порядок «Core-first, local-second» без компенсации (зеркально к проблеме create в F-0015).

## Радиус поражения
Редкий, только при сбое на узком окне; рассинхрон статуса проекта.

## Направление фикса (1-2 строки, НЕ реализовано)
Локальный delete в транзакции, Core-archive после успеха (или реконсиляция статусов); History — до `delete()`.
