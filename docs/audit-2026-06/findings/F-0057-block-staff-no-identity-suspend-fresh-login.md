---
id: F-0057
flow: staff-management
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin, rusaiauth]
status: open
---
## Симптом
Блокировка сотрудника в rusaifin не вызывает suspend в identity (rusaiauth). Заблокированный (в т.ч. уволенный) пользователь может выполнить новый OIDC-login и получить свежий валидный токен. Это write-side к reader-side F-0027 (там — уже-выпущенный suspend не валит live-сессию; здесь — suspend не выпускается вовсе).

## Доказательства (file:line)
- `app/Services/User/UserService.php:194-212` — в `disable()` нет обращений к identity.
- `grep` по `suspend`/`RusaiauthClient`/`identity.*write` в `app/` — 0 совпадений; интеграции suspend в rusaifin нет (в отличие от password-sync `RusaiauthPasswordSyncClient`, `UserService.php:501,541`).
- `app/Http/Middleware/UserIsNotDisabled.php:21` — блокирует доступ ТОЛЬКО внутри rusaifin (по локальному `disabled`); identity/SSO продолжает выдавать токены.
- `rusaiauth LoginController` проверяет `status==='active'` при login (F-0027) — раз rusaifin не ставит suspend, identity остаётся `active` → fresh login проходит.

## Триггер / repro
Заблокировать полевого юзера → он логинится заново через `sso.rusaifin.ru` → получает токен. rusaifin закрыт middleware; identity-логин и любой доступ, не требующий завершённых Core-memberships, остаются открыты.

## Корневая причина (гипотеза)
Block — однодоменная локальная мутация; identity не уведомляется (нет клиента suspend).

## Радиус поражения
Заблокированный сохраняет способность аутентифицироваться по SSO. Практический доступ к sklad/Core частично смягчён завершением Core-memberships в `detachFromProjectsAndPoints`, но identity-аккаунт остаётся живым — фрагильная защита, опирающаяся только на detach + per-service middleware.

## Направление фикса (1-2 строки, НЕ реализовано)
Добавить identity-suspend вызов (scope identity write) в `disable(true)` и unsuspend в `disable(false)`, по образцу password-sync.
