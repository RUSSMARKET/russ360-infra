---
id: F-0031
flow: password-recovery-sync
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaisklad_back, rusaiauth]
status: open
---
## Симптом
Смена пароля sklad-пользователем из кабинета (`PUT /api/v1/user/password`) пишет только `users.password`, без пуша в `identity_users.password_hash`. После смены вход по новому паролю через SSO не работает. Это АКТИВНЫЙ путь (не legacy).

## Доказательства (file:line)
- `rusaisklad_back/app/Services/User/UserContext.php:127-128` — `$this->user->password = Hash::make($newPassword); $this->user->save();` — нет identity-sync.
- `rusaisklad_back/app/Http/Controllers/API/User/UserController.php:120` — `changePassword` делегирует в этот метод; роут активен под `['auth:oauth','user.not_disabled']`.
- Контраст: `rusaifin/app/Services/User/UserService.php:501` вызывает `RusaiauthPasswordSyncClient` (симметричный путь синхронит).

## Триггер / repro
Sklad-юзер меняет пароль в кабинете → новый hash в `users.password`, identity не тронут → SSO по новому паролю 401, старый пароль продолжает работать в SSO.

## Корневая причина (гипотеза)
Bidirectional sync доведён до rusaifin (admin + cabinet), но кабинетный путь sklad не покрыт (в sklad вообще нет исходящего sync-клиента).

## Радиус поражения
Все sklad-пользователи, меняющие пароль из кабинета. Активный, не латентный путь → P1.

## Направление фикса (1-2 строки, НЕ реализовано)
Добавить identity-sync в `UserContext::changePassword` (зеркально rusaifin `UserService::changePassword`), с теми же fatal/rollback-семантиками.
