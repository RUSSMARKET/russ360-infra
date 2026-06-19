---
id: F-0058
flow: staff-management
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
В `grant()` испытательного периода удалённые Core-write (создание Employee + membership + assignment по нескольким точкам) выполняются ВНУТРИ локального `DB::transaction`. При падении на N-й точке локальный rollback откатывает rusaifin-строки, но уже выполненные Core-write по точкам 1..N-1 (и созданный Employee) не компенсируются. Тот же анти-паттерн, что F-0022, в другом месте.

## Доказательства (file:line)
- `app/Services/Staff/AgentTestPeriodService.php:78-93` — `DB::transaction(function(){ … app(EnsureCoreEmployeeLinked::class)->execute($target); foreach ($pointIds as $pointId) { (new PointService($pointId))->addAgent($target); } … })`.
- `app/Services/Project/PointService.php:226-243` — `addAgent` делает несколько Core HTTP-write (`EnsureCoreEmployeeLinked` create, `ensureActiveProjectMembershipForAssignment`, `coreCreateAssignment`); ошибки пробрасываются (`PointService.php:289` `throw $e`).

## Триггер / repro
Выдать стажёрство с 2+ точками; Core отвечает ошибкой (не conflict) на второй точке. Локально период/`is_trainee` откатятся, в Core останутся Employee + assignment первой точки → рассинхрон rusaifin↔Core.

## Корневая причина (гипотеза)
Смешение нетранзакционных удалённых HTTP-вызовов с локальной БД-транзакцией; нет saga/компенсации.

## Радиус поражения
Частичные Core-привязки у юзера, который локально снова «без стажировки». Проявляется при сбое Core в середине многоточечной выдачи.

## Направление фикса (1-2 строки, НЕ реализовано)
Вынести Core-write за пределы `DB::transaction` либо добавить компенсацию (end созданных assignments/Employee) в catch.
