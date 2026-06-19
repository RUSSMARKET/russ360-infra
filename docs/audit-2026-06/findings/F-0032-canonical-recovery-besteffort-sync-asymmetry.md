---
id: F-0032
flow: password-recovery-sync
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaiauth, rusaifin, rusaisklad_back]
status: open
---
## Симптом
Канонический recovery (rusaiauth) обновляет `identity_users.password_hash`, затем best-effort синхронит в legacy — и возвращает 200 ДАЖЕ если legacy-sync провалился. `users.password` остаётся старым, пользователю отдан успех → расхождение password_hash↔password.

## Доказательства (file:line)
- `rusaiauth/app/Http/Controllers/Auth/Recovery/RecoveryController.php:138` — обновляет `password_hash`; `:143-149` best-effort sync; `:159-163` возвращает `status:true` независимо от `$rusaifinOk/$rusaiskladOk` (только логируются `:151-157`).
- `rusaiauth/app/Domain/Identity/Support/Password/LegacyPasswordSyncClient.php:66-72,91-96` — ловит и глотает все ошибки → `false`, не throw.
- Контраст: обратное направление (rusaifin→identity) fatal с rollback (`rusaifin/app/Infrastructure/Identity/RusaiauthPasswordSyncClient.php:60,73,83` throw).

## Триггер / repro
rusaifin/sklad недоступны/5xx в момент `/v1/recovery/password` → identity обновлён, legacy нет, юзер видит успех. SSO по новому паролю работает (identity), но legacy-проверки пароля — со старым hash.

## Корневая причина (гипотеза)
Сознательный best-effort на canonical-стороне vs fatal на legacy-стороне; нет outbox/ретрая → расхождение при флапе legacy. Комментарий «operator can re-run later» = ручная компенсация.

## Радиус поражения
Recovery во время недоступности legacy-сервисов; молчаливое расхождение, ограниченное окнами недоступности.

## Направление фикса (1-2 строки, НЕ реализовано)
Outbox/ретрай legacy-sync, либо предупреждение в ответе recovery, либо привести политику к симметрии (осторожно: fatal заблокирует сброс при недоступности legacy).
