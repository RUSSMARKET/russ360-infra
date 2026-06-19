---
id: F-0072
flow: user-profile-me
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

В одном `/auth/me`-ответе rusaifin top-level `role` отражает глобальный `users.role_id`, а `memberships[].role` (и роль текущего проекта) — из Core. При несовпадении глобальной и проектной роли в payload одновременно лежат два разных значения роли без указания, какое авторитетно.

## Доказательства (file:line)

- top-level: `rusaifin/app/Http/Controllers/Registration/AuthController.php:96` (`'role' => $user->role->code`) и `:116` (`userPayload.role` = `$user->role->code`) — глобальная Eloquent-роль.
- memberships из Core: `rusaifin/app/Services/Project/ProjectBootstrapPayloadFactory.php` (`projectMembershipProvider->listForEmployeeExternalId`, `membership->role`).
- authz в rusaifin полностью глобальный (нет `getEffectiveRole`; проверки по `role_id`), т.е. top-level `/me`-роль СОГЛАСОВАНА с authz; рассинхрон только между top-level `role` и `memberships[].role` внутри payload.

## Триггер / repro

Юзер с глобальной ролью X и Core-membership-ролью Y в текущем проекте: `/me` → `role: X`, `memberships[current].role: Y`. Фронт, если читает membership-роль для UI текущего проекта, разойдётся с top-level.

## Корневая причина (гипотеза)

Известная дихотомия global vs membership (кросс-ссылка F-0063, audit 2026-05-18:141), специфичное проявление — оба значения в одном `/me` payload без пометки авторитетности. Поскольку authz rusaifin = глобальная роль, top-level авторитетна; membership-роль информационна.

## Радиус поражения

UI-элементы rusaifin-фронта, опирающиеся на membership-роль текущего проекта при глобально-ином role. Минор (authz не затронут — отсюда P3).

## Направление фикса

Задокументировать контракт (authz rusaifin = глобальная роль), либо добавить явное `current_project_role` отдельным полем, чтобы фронт не путал top-level и membership роль.
