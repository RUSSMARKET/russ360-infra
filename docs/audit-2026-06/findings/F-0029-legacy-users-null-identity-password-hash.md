---
id: F-0029
flow: login-otp
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaiauth, rusaifin]
status: open
---
## Симптом
Legacy-юзеры, ни разу не менявшие пароль после M2, не могут войти по паролю через SSO (`identity_users.password_hash` = NULL), хотя SMS-OTP работает. Фронт показывает неотличимое «Invalid credentials».

## Доказательства (file:line)
- `rusaiauth/app/Http/Controllers/Auth/LoginController.php:41-46` — `if ($user->password_hash === null) → 'Invalid credentials'`; OTP-ветка (`:78-180`) `password_hash` не смотрит.
- Bidirectional sync пушит `password_hash` только ПРИ смене пароля (on-change), разового backfill из `rusaifin.users.password` в `identity_users.password_hash` не было.

## Триггер / repro
Полевой сотрудник, заведённый до sync и не менявший пароль через кабинет rusaifin → `password_hash` в identity = NULL → логин по паролю всегда «неверные данные», по SMS — ок.

## Корневая причина (гипотеза)
НОВЫЙ аспект к известной заметке про sync: проблема не «сломалось при смене», а в том, что для никогда-не-менявших пароль `identity.password_hash` пуст с самого backfill identity. Маскируется одинаковым сообщением (нельзя отличить «нет пароля» от «неверный пароль»); диагностируется только по audit reason=`no_password_set`.

## Радиус поражения
Все legacy-юзеры без смены пароля после M2 (масса полевых). UX: «пароль не подходит», лечится только OTP/сбросом.

## Направление фикса (1-2 строки, НЕ реализовано)
One-off backfill `password_hash` из `rusaifin.users.password` (если хэши совместимы), либо явный код `no_password_set` на фронт с подсказкой «войдите по SMS».
