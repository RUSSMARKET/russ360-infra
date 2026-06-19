---
id: F-0030
flow: password-recovery-sync
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin, rusaisklad_back]
status: open
---
## Симптом
Legacy-эндпоинты восстановления пароля (`POST /api/passwordrecovery` в rusaifin и rusaisklad) меняют пароль ТОЛЬКО в локальной `users.password`, без пуша в `identity_users.password_hash`. После такого сброса вход по новому паролю через SSO/OAuth не работает (rusaiauth держит старый hash) — работает только SMS-OTP. Эндпоинты живы и без auth.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Registration/RestorePasswordController.php:272-273` — `$user->update(['password' => Hash::make($validated['new_password'])])` — нет вызова `RusaiauthPasswordSyncClient`. Контроллер помечен `@deprecated M2.1` (`:16-18`), но активен (`routes/api.php:69-72`).
- `rusaifin/app/Models/User/User.php:64` — `booted()` ловит только `deleting`; нет `updating/saving` → неявного sync нет.
- `rusaisklad_back/app/Services/PasswordRecovery/PasswordRecoveryService.php:102` — `$user->update(['password' => Hash::make($newPassword)])` без identity-sync; в sklad исходящего sync-клиента к rusaiauth НЕТ вообще (`find -name '*PasswordSync*'` пусто).

## Триггер / repro
Любой клиент, всё ещё ходящий на legacy `passwordrecovery` (rusaifin/sklad), сбрасывает пароль → `users.password` обновлён, `identity_users.password_hash` старый → SSO-логин 401.

## Связь с фактами (severity)
**verified**: и fintech (`src/pages/forgot_password/api/index.ts`), и sklad-front (`src/pages/forgot_password/api/index.ts`) уже ходят на канонический `/api/v1/recovery/*` (rusaiauth). Поэтому это **латентная мина**, а не активная поломка — отсюда P2, а не P0. Риск реализуется при старом/кэшированном клиенте, мобильном приложении или прямом вызове API.

## Корневая причина (гипотеза)
Два параллельных recovery-потока; legacy не довели до симметрии с bidirectional sync (`UserService::setPassword/changePassword` синхронят, прямой `$user->update` — нет).

## Радиус поражения
Любой пользователь, прошедший legacy-флоу восстановления (rusaifin или sklad). Расхождение паролей; SSO ломается до следующей canonical-смены.

## Направление фикса (1-2 строки, НЕ реализовано)
Подтвердить, что ни один клиент не ходит на legacy `passwordrecovery`, и снять роуты; либо заменить прямой `$user->update` на `UserService::setPassword` (которая синхронит в identity).
