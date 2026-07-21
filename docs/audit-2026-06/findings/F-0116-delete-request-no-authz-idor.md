---
id: F-0116
flow: requests-cards-magnit
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

`DELETE /api/request/{id}` без какой-либо проверки прав/владения/проекта: любой авторизованный (не-disabled) пользователь, включая рядового агента, может удалить ЛЮБУЮ заявку (`product_history`) по id. Аналог F-0106 (delete-ruchnik), но для заявок.

## Доказательства (file:line)

- `routes/api.php:371` — `Route::delete('request/{id}', ...)->middleware(['auth:oauth', UserIsNotDisabled::class])` — НЕТ `CheckPermission`, НЕТ `ResolveCurrentProject`.
- `app/Http/Controllers/Product/RequestController.php:702-724` (`deleteRequest`) — валидирует только `id|exists:product_history,id`, затем `ProductHistory::find($id)->delete()` без проверки роли/владельца (`agent_id`)/проекта. История пишется постфактум.

## Триггер / repro

Любой агент: `DELETE /api/request/<чужой_id>` → 200, заявка чужого агента/проекта удалена.

## Корневая причина (гипотеза)

Роут навешен только на `auth:oauth`+`UserIsNotDisabled`; объектная авторизация в методе отсутствует (паттерн повторяет F-0106/F-0107 — целый блок requests/ruchnik эндпоинтов под одним лишь auth-гейтом).

## Радиус поражения

Деструктивная межпроектная утечка: уничтожение заявок любого агента/проекта. P1. Усилится при возврате свитчера (ложное ощущение изоляции).

## Направление фикса (не реализовано)

Добавить `CheckPermission` + объектную проверку: агент — только свои (`agent_id === actor`), привилегированные роли — только в зоне (membership/`resolveVisibleUserIds`). Как в соседних scoped-методах.

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`routes/api.php:385` — `DELETE request/{id}` без `CheckPermission`; контроллер валидирует только `exists` и делает `find($id)->delete()` без проверки владения.
