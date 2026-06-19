---
id: F-0027
flow: login-otp
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaiauth, rusaifin, rusaisklad_back]
status: open
---
## Симптом
Деактивация identity (`status != active`) после логина не прерывает живую сессию: access-токен работает до exp, refresh-grant продолжает выдавать новые токены. Resource-серверы знают только локального `users`, статус identity не читают.

## Доказательства (file:line)
- `rusaiauth/app/Http/Controllers/Auth/LoginController.php:55,153,197` — `status==='active'` проверяется ТОЛЬКО в момент login/otp.
- `rusaifin/app/Providers/AppProvider.php:137` и `rusaisklad_back/app/Providers/AppServiceProvider.php:125` — guard резолвит User по `sub` без обращения к `identity_users` и без проверки статуса.
- Refresh-grant rusaiauth не привязан к live-проверке status.

## Триггер / repro
identity юзера ставят `status='suspended'` после логина. Access-токен живёт до exp, refresh продлевает — оба resource-сервера продолжают пускать.

## Корневая причина (гипотеза)
Статус — gate только на этапе аутентификации в rusaiauth; нет revoke токенов при деактивации, нет проверки на resource-серверах. (Родственно известному «logout без revoke».)

## Радиус поражения
Все защищённые эндпоинты обоих resource-серверов; окно = время жизни refresh-токена.

## Направление фикса (1-2 строки, НЕ реализовано)
При деактивации identity — revoke Passport-токенов; опционально короткий TTL/introspection.
