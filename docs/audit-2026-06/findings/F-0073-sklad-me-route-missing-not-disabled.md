---
id: F-0073
flow: user-profile-me
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом

`/api/v1/auth/me` защищён только `auth:oauth`, без `user.not_disabled`, тогда как группа `/user/*` требует `user.not_disabled`. Заблокированный (`disabled=1`) пользователь с валидным токеном получает полный bootstrap-профиль (роль, проекты, memberships).

## Доказательства (file:line)

- `rusaisklad_back/routes/api.php:174-175` — `/me` → `->middleware('auth:oauth')` (без `not_disabled`).
- Контраст: `routes/api.php:187` — `Route::prefix('user')->middleware(['auth:oauth', 'user.not_disabled'])`.

## Триггер / repro

Пользователь с `disabled=1` и валидным (не отозванным) токеном дёргает `/api/v1/auth/me` → 200 с собственным профилем. Рабочие эндпоинты под `user.not_disabled`/`current.project` его далее отсекут.

## Корневая причина (гипотеза)

`/me` задуман как «лёгкий» bootstrap под `auth:oauth`, но утечка профиля заблокированному не предусмотрена. Один класс с F-0026/F-0027 (неполное применение disabled/suspend в sklad).

## Радиус поражения

Заблокированные аккаунты; низкий — payload собственный (не чужой), реальные действия блокируются. Минор.

## Направление фикса

Добавить `user.not_disabled` на `/me`, либо отдавать disabled-флаг и пустой контекст для заблокированных. Кросс-ссылка F-0026, F-0027.
