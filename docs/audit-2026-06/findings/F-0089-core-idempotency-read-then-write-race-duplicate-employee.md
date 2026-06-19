---
id: F-0089
flow: core-crud
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaicore]
status: open
---

## Симптом
`EnsureIdempotency` использует паттерн read-then-write без атомарной брони ключа. Две одновременные записи с одним `Idempotency-Key` и одинаковым телом обе видят `$existing === null`, обе выполняют сайд-эффект, обе пишут результат (`insertOrIgnore` второй игнорируется, но эффект уже выполнен дважды). Для membership/assignment второй дубль ловит partial-unique индекс БД (→409, безопасно), но `CreateEmployee` не имеет естественного dedup → гонка создаёт ДВА employee.

## Доказательства (file:line)
- `rusaicore/.../EnsureIdempotency.php:35` — read по `idempotency_key` → `:50` выполнение `$next` → `:54` `insertOrIgnore`; нет `lockForUpdate`/insert-first до выполнения.
- `Application/.../CreateEmployee.php:23-46` — нет dedup по phone/email; `identity_user_id` unique только если задан.
- Контраст: `project_memberships_employee_project_open_uidx`, `ola_employee_location_open_uidx` (partial unique) ловят дубль membership/assignment → 409.

## Триггер / repro
rusaifin ретраит `POST /api/v1/employees` на сетевом блипе; оба запроса с одним `Idempotency-Key` долетают почти одновременно → оба проходят read=null → два Core-employee. Усугубляет известные orphan/duplicate-employee регрессии (memory `seed_employees_command_bug`, `stage2_orphan_users_recurring_regression`).

## Корневая причина (гипотеза)
Read-then-write без атомарного «забронировать ключ» (unique на `idempotency_key` есть, но используется только post-factum через insertOrIgnore). Тот же класс, что F-0042 (sklad receipt double-credit), но на уровне Core-middleware. Защищает только то, что прикрыто backing-constraint'ом БД.

## Радиус поражения
Employee-creation (нет естественного ключа в БД) и любой будущий Core-write без backing-constraint.

## Направление фикса
Insert-first идемпотентность: вставить ключ со статусом «in-flight» под unique ДО выполнения, при коллизии — ждать/реплеить (или `SELECT … FOR UPDATE`). Отдельно решить, нужен ли естественный dedup employee. См. F-0042.
