---
id: F-0088
flow: core-crud
dimension: architecture-drift
severity: P1
confidence: confirmed
services: [rusaicore]
status: open
---

## Симптом
Ни один из 10 write-роутов канонического writer'а (POST/PATCH ×5 сущностей) не проверяет OAuth-scope. Любой валидный токен с audience=core — любого scope, от любого клиента, включая чистый `client_credentials` S2S — может писать/менять все 5 Core-сущностей. Least-privilege на единственной точке истины записи отсутствует.

## Доказательства (file:line)
- `rusaicore/routes/api.php:19` — группа `/v1` под `['auth:oauth', EnsureIdempotency::class]`; никаких `scope:`/`can:` middleware.
- `rusaicore/routes/api.php:32-55` — все write-роуты (employees/projects/operational-locations/project-memberships/operational-location-assignments) без scope-гейта.
- `OAuthPrincipal.php` — `hasScope()/hasAllScopes()/hasAnyScope()` определены, но `grep -rn "hasScope|hasAllScopes|hasAnyScope" app | grep -v OAuthPrincipal` → пусто (нигде не вызываются).
- В Api/V1-контроллерах нет обращения к `$principal->scopes`/`abort(403)`.

## Триггер / repro
S2S-клиент с токеном, предназначенным только под чтение (или иной scope), делает `POST /api/v1/project-memberships` → 201. Скомпрометированный/мисконфигнутый resource-server-токен любого потребителя (fin/sklad/auth) пишет в Core напрямую, минуя всю бизнес-логику guard'ов rusaifin. Если user-PKCE-токены несут aud=core — поле может напрямую создать себе membership-роль менеджера (требует верификации audience в фазе 2).

## Корневая причина (гипотеза)
Авторизация остановлена на аутентификации (`auth:oauth` лишь валидирует JWT). Scope-gate спроектирован (helpers на принципале), но не подключён к роутам/контроллерам — недоведённая фича. `sub===aud` нормализация client_credentials есть, но без scope-проверки защиты записи не добавляет.

## Радиус поражения
Все 5 Core-сущностей, вся платформа (Core — единственный writer). Нарушение least-privilege для всех S2S-интеграций.

## Направление фикса
Middleware-gate `scope:core.write` (или per-entity scopes) на write-группе либо `$principal->hasScope(...)` в контроллерах/Actions. Согласовать с владельцем целевую модель scopes (S2S vs user-token) и проверить audience user-токенов.
