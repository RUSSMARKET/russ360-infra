---
id: F-0026
flow: login-otp
dimension: correctness
severity: P2
confidence: likely
services: [rusaisklad_back]
status: open
---
## Симптом
Заблокированный (`disabled`) пользователь rusaisklad сохраняет доступ к inventory/projects/analytics/admin эндпоинтам: guard не проверяет `disabled`, а группа этих роутов не несёт `user.not_disabled`.

## Доказательства (file:line)
- `rusaisklad_back/app/Providers/AppServiceProvider.php:125-141` — guard резолвит `User` по `identity_user_id` и возвращает без проверки `disabled`.
- `rusaisklad_back/routes/api.php` — `Route::middleware(['auth:oauth', 'current.project'])->group(...)` оборачивает `$registerInventoryRoutes/$registerAnalyticsRoutes/$registerSkuRoutes` БЕЗ `user.not_disabled`; только `Route::prefix('user')->middleware(['auth:oauth', 'user.not_disabled'])` защищён.
- Контраст (verified): в rusaifin ВСЕ 237 `auth:oauth`-роутов несут `UserIsNotDisabled` — там дефекта НЕТ.

## Триггер / repro
Sklad-пользователю ставят `disabled` → с уже выпущенным токеном (или новым логином, т.к. identity status может быть active) он дёргает `/api/v1/inventory/*`, `/projects/*` → 200.

## Корневая причина (гипотеза)
Проверка `disabled` навешена точечно только на `/user`-группу, не на основной массив inventory/projects; guard её не дублирует.

## Радиус поражения
Все защищённые inventory/projects/analytics/admin эндпоинты sklad для заблокированного пользователя. (rusaifin не затронут — verified.) confidence likely: требует подтверждения семантики «disabled» в sklad (локальный флаг vs Core membership).

## Направление фикса (1-2 строки, НЕ реализовано)
Навесить `user.not_disabled` на группу `['auth:oauth','current.project']` (или проверять `disabled` в guard), как сделано в rusaifin глобально.
