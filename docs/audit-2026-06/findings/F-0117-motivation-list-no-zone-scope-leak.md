---
id: F-0117
flow: motivation
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

List-эндпоинты мотивации отдают записи ВСЕХ агентов по ВСЕМ проектам без какого-либо скоупа по зоне/проекту/роли-владельцу: носитель `*.get`-пермишена (в т.ч. GROUP_LEADER) видит штрафы/компенсации/«приведи друга» всей компании.

## Доказательства (file:line)

- `app/Http/Controllers/Motivation/PenaltiesController.php:34-40` (`getPenalties`) — `Penalties::get()` без единого `where`.
- `app/Http/Controllers/Motivation/CompensationController.php:34` (`getCompensations`) — `Compensations::get()`.
- `app/Http/Controllers/Motivation/BringFriendController.php:34` (`getBringFriend`) — `BringFriend::get()`.
- `{id}`-варианты (`getUserPenalties` и т.п.) принимают `user_id` из URL без проверки членства → IDOR на чтение по любому юзеру.

## Триггер / repro

GROUP_LEADER с `penalties.get`: `GET /api/penalties` → весь список штрафов всех агентов всех проектов.

## Корневая причина (гипотеза)

Скоуп по зоне не применён; в схеме мотивации (`2025_04_21_135214_create_sallary_tables`) НЕТ `project_id` — таблицы ключуются только на `user_id`/`from_user_id`. Проектный скоуп структурно невозможен без миграции+бэкфилла. `ResolveCurrentProject` на этих роутах — косметика (проверяет лишь наличие проекта, контроллер его не читает).

## Радиус поражения

Межпроектная утечка мотивационных/зарплатных данных всех агентов. P2. Возврат свитчера НЕ изменит (нет проектной привязки) — даёт ложное ощущение изоляции.

## Направление фикса (не реализовано)

Скоупить list по зоне viewer'а (`resolveVisibleUserIds`/`accessiblePointIds`), `{id}`-чтение — проверять членство target в зоне. Для проектной изоляции — отдельно решить про `project_id` на таблицах (миграция, с владельцем).
