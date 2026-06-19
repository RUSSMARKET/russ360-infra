---
id: F-0033
flow: password-recovery-sync
dimension: correctness
severity: P2
confidence: likely
services: [rusaiauth, rusaifin]
status: open
---
## Симптом
Recovery-sync ключуется по `users.phone`. При email-канале (телефон в identity может отсутствовать) legacy молча не обновляется. При несовпадении формата телефона между сервисами sync даёт `user_not_found` при существующем юзере и тихо пропускает (best-effort).

## Доказательства (file:line)
- `rusaiauth/app/Http/Controllers/Auth/Recovery/RecoveryController.php:143-149` — sync выполняется только если `$user->phone` непустой; при email-recovery без телефона legacy не трогается, но `status:true`.
- `rusaifin/app/Http/Controllers/Internal/Users/SetPasswordController.php:35` — нормализует `preg_replace('/[^0-9]+/','')` и матчит `where('phone',$phone)`; `users.phone` в rusaifin исторически хранится как `intval(...)` (`RestorePasswordController.php:112`), формат отличается от нормализатора rusaiauth (см. F-0020).

## Триггер / repro
Юзер с телефоном в `users.phone` в формате, отличном от нормализованного rusaiauth → recovery обновит identity, legacy-sync вернёт 404 (не найден) → best-effort проглотит → расхождение.

## Корневая причина (гипотеза)
Нет общего канонического ключа sync (используется phone, форматы которого исторически разные); `identity_user_id`/`external_id` как ключ не используется.

## Радиус поражения
Пользователи с нестандартным/«грязным» телефоном; точный объём требует проверки данных.

## Направление фикса (1-2 строки, НЕ реализовано)
Синхронизировать по `identity_user_id`/`external_id` вместо phone; либо единая нормализация телефона на обеих сторонах.
