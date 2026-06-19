---
id: F-0098
flow: notifications-redirect
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`GET /api/redirect/to/{code}` без auth делает `redirect()->to($redirect->redirect_to)` на произвольный URL — классический open-redirect вектор (фишинг с легитимного домена rusaifin).

## Доказательства (file:line)
- `rusaifin/routes/api.php:500` — `redirect/to/{code}` без auth.
- `rusaifin/app/Http/Controllers/System/RedirectController.php:350` — `redirect()->to($redirect->redirect_to)`.

## Триггер / repro
`GET /api/redirect/to/{code}` → 302 на внешний URL. Нюанс, снижающий severity: `redirect_to` берётся из строки БД, создаваемой только админом (`createRedirect` под `CheckPermission:admin`), не из параметра запроса → произвольный URL подставит только админ. Поэтому P3.

## Корневая причина (гипотеза)
Нет валидации/whitelist домена `redirect_to`; редирект на любой внешний адрес.

## Радиус поражения
Фишинг через доверенный домен; ограничено тем, что URL задаёт только админ.

## Направление фикса
Whitelist/валидация домена `redirect_to` при создании либо exit-warning-страница для внешних доменов.
