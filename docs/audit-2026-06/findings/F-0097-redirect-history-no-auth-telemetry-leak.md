---
id: F-0097
flow: notifications-redirect
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`GET /api/redirect/history/{id}` без middleware отдаёт всю `RedirectHistory` по `redirect_id` без проверки прав. История содержит IP, user-agent, язык, referrer переходивших — утечка телеметрии по перебору id.

## Доказательства (file:line)
- `rusaifin/routes/api.php:502` — `redirect/history/{id}` БЕЗ middleware (соседние redirect-CRUD-роуты 503-507 под `admin`).
- `rusaifin/app/Http/Controllers/System/RedirectController.php:486-499` — `RedirectHistory` по `redirect_id` без authz.
- `…/RedirectController.php:337-346` — история содержит IP/UA/язык/referrer.

## Триггер / repro
`GET /api/redirect/history/1` без токена → JSON со списком IP/UA/referrer. Перебор последовательных целых `id` → выгрузка всей телеметрии переходов.

## Корневая причина (гипотеза)
Роут не закрыт тем же middleware-стеком, что остальной redirect-CRUD (забытый guard).

## Радиус поражения
Утечка телеметрии всех redirect-кампаний (IP/UA/referrer пользователей).

## Направление фикса
Добавить `['auth:oauth', UserIsNotDisabled, ResolveCurrentProject, CheckPermission:admin]` на роут 502.
