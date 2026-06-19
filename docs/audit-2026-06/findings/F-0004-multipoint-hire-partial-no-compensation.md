---
id: F-0004
flow: hiring-onboarding
dimension: data-integrity
severity: P2
confidence: likely
services: [rusaifin, rusaicore]
status: open
---
## Симптом
При оформлении на несколько точек сразу ошибка Core на N-й точке оставляет частично применённое состояние без отката: `role_id` уже сменён и сохранён, Core-employee создан, ассигнации на точки 1..N-1 уже записаны в Core, N+1..M — нет.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Staff/StaffRegistrationController.php:949-950` — `$agent->role_id = ...; $agent->save();` (роль фиксируется до циклов записи).
- `:959-978` и `:1041-1067` — `foreach($validated['points_id'] as $point_id) { (new PointService($point_id))->addAgent/setGroupLeader($agent); }` без `DB::transaction` и без компенсации; каждый `addAgent` делает несколько Core-write (membership + assignment).
- `PointService.php:289-291`, `ProjectService.php:337-349` — не-conflict Core-ошибки ре-бросаются наружу, прерывая цикл на середине.

## Триггер / repro
`setRegistrationRole` с `points_id=[A,B,C]`, где запись по B падает (Core 5xx / network). A уже привязана в Core, C — нет. Повтор с тем же набором идемпотентен (conflict→no-op), но при изменённом наборе точек остаётся «хвост».

## Корневая причина (гипотеза)
Мультиресурсная запись через сеть без саги/компенсации; локальный `role_id` коммитится отдельно от удалённых Core-записей. (БД-транзакция тут не помощник — Core внешний.)

## Радиус поражения
Мульти-точечное оформление агентов/групп-лидеров. Одиночное оформление практически не затронуто.

## Направление фикса (1-2 строки, НЕ реализовано)
Собирать результат по каждой точке; при провале возвращать частичный статус с перечнем непривязанных точек, либо предварительно валидировать все точки до начала записи.
