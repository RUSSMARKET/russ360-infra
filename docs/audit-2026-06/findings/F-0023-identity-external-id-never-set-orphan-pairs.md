---
id: F-0023
flow: registration-auth
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaiauth, rusaifin]
status: open
---
## Симптом
Связь `identity_users → users` (`external_id`) НЕ устанавливается при регистрации; линковка односторонняя и только на этапе set-password. Брошенные регистрации оставляют несвязанные orphan-пары записей.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Internal/Registration/RegistrationInternalController.php:83` — `init` возвращает `rusaifin_user_id`, но `rusaiauth/.../RegistrationController.php:91-97` (`startPhone`) его игнорирует (проверяет только `status`); `IdentityUser.external_id` при регистрации не пишется.
- Обратная связь `users.identity_user_id` пишется лишь в set-password и лишь если `identity_user_id` передан (`RegistrationInternalController.php:103-105`).

## Триггер / repro
Регистрация прервалась после `init`/`verifyCode`, но до `setPassword` → shell `users` (без password) и `identity_users` (без password_hash), НЕ связанные через `external_id`. Orphan-пара, обнаруживаемая только по совпадению phone (который может различаться — см. F-0020).

## Корневая причина (гипотеза)
Линковка отложена до финального шага и однонаправленна; промежуточные shell-записи остаются несвязанными.

## Радиус поражения
Брошенные регистрации → пары orphan-записей; усложняет reconcile, особенно в сочетании с phone-mismatch.

## Направление фикса (1-2 строки, НЕ реализовано)
Писать `external_id = rusaifin_user_id` в `IdentityUser` сразу после `init`; чистить/маркировать незавершённые shell-пары.
