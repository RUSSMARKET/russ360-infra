---
id: F-0121
flow: point-agent-binding
dimension: correctness
severity: P3
confidence: likely
services: [rusaifin, rusaicore]
status: open
---

## Симптом

`POST|DELETE /api/product/{product_id}/point/agent` (`add/deleteProductPointAgents`) не проверяет принадлежность точек проекту/зоне актора: носитель `point.management` (RD/PM/support и т.д.) массово правит привязки агентов на точках ЛЮБОГО проекта продукта, не только своих. Authz-измерение того же эндпоинта, что F-0010/F-0078 (там — атомарность/фиктивные счётчики).

## Доказательства (file:line)

- `routes/api.php` — `product/{product_id}/point/agent` под `CheckPermission:point.management` (ролевой гейт есть).
- `app/Http/Controllers/Project/PointController.php:783-...` (`addProductPointAgents`) и `:909-...` (`deleteProductPointAgents`) — валидируют `product_id|exists` и что users — агенты; затем цикл по парам без `hasProjectUser`/`hasPointUser`/проверки `core_location_external_id` точки в зоне актора (в отличие от `addPointAgent`/`deletePointAgent`, где есть `hasPointUser`).

## Триггер / repro

RD/PM проекта A с `point.management`: вызвать sync для продукта, чьи точки в проекте B → привязки/отвязки агентов на чужих точках.

## Корневая причина (гипотеза)

Bulk-sync продукта оперирует ВСЕМИ точками продукта глобально; объектный (point/project-membership) гейт, присутствующий в одиночных point-agent методах, здесь пропущен.

## Радиус поражения

Кросс-проектная правка агентских привязок привилегированными ролями. P3 (ограничено `point.management`). Усилится при возврате свитчера.

## Направление фикса (не реализовано)

Перед sync фильтровать/валидировать целевые точки по зоне актора (`hasPointUser`/membership), как в `addPointAgent`. Связано: F-0010, F-0078 (атомарность того же пути), F-0008.
