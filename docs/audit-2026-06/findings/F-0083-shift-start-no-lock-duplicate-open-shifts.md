---
id: F-0083
flow: shift-planning
dimension: data-integrity
severity: P2
confidence: likely
services: [rusaifin]
status: open
---

## Симптом
`POST /api/shift/start` проверяет «смена уже активна» read-then-write без блокировки/транзакции; двойной тап/ретрай может создать две открытые смены (`shifts` с `end_time = null`) у одного агента.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/.../ShiftController::startShifts` (≈:230) → `rusaifin/app/Services/User/ShiftService.php:1234` `start()`: guard `if ($this->isActive())` затем `Shift::Create(...)` (≈:1242) — без транзакции/`lockForUpdate`.
- `ShiftService::isActive` (≈:1080) — `SELECT ... orderBy('start_time','desc')->first()` (read), не блокирует.
- Миграция `…create_shifts_table.php` — нет уникального индекса на «одну открытую смену на агента» (`(user_id) WHERE end_time IS NULL`); БД дубль не ловит (контраст: `planned_shifts.unique(user_id, scheduled_start_time)`).

## Триггер / repro
Два параллельных `shift/start` от агента в окне до коммита первого → оба проходят `isActive()==false` → две открытые смены. Затем `end`/`status` берут `orderBy('start_time','desc')->first()` → вторая «теряет» первую открытую (висячая запись часов).

## Корневая причина (гипотеза)
Класс F-0001: проверка state-machine на stale-чтении без `lockForUpdate`+re-check внутри транзакции; нет БД-инварианта на единственную открытую смену.

## Радиус поражения
Целостность учёта смен/отработанных часов агента; искажение отчётов по сменам.

## Направление фикса
Обернуть `start` в транзакцию с `lockForUpdate` по последней смене агента + re-check `isActive`, либо частичный unique-индекс на одну открытую смену.
