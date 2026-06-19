---
id: F-0040
flow: inventory-issue-writeoff
dimension: data-integrity
severity: P3
confidence: confirmed
services: [rusaisklad_back]
status: open
---
## Симптом
Защита остатков (`qty_total`/`qty_reserved`) от ухода в минус держится исключительно на application-level guard. На уровне БД пола нет: `unsignedBigInteger` в Postgres компилируется в обычный signed `bigint`, отрицательные значения сохраняются без ошибки. Любой будущий путь декремента без guard молча уведёт остаток в минус, а тесты на sqlite это не поймают.

## Доказательства (file:line)
- `database/migrations/2026_02_06_000001_create_inventory_balances_table.php:20-21` — `$table->unsignedBigInteger('qty_total')` / `qty_reserved`; CHECK-constraint `>= 0` отсутствует.
- Прод — Postgres (`config/database.php` default `pgsql`; модель использует `ilike` в `app/Models/InventoryBalance.php`). В Postgres-грамматике Laravel `unsignedBigInteger` → `bigint` (unsigned не поддерживается) — пол не enforced.
- Тесты идут на sqlite (`phpunit.xml` / `.env.example`), где unsigned тоже не enforced → регрессия в guard'е не ловится ни БД, ни тестом.
- Текущие пути декремента (`InventoryService::issue` ~`:1071-1143`, `writeoff` ~`:1158-1227`, `InventoryWriteoffRequestService` approve) guard'ятся `ensureAvailable`/`qty_reserved>=qty` под локом — поэтому сейчас latent, не активный.

## Триггер / repro
Будущий рефактор или новый метод, декрементящий `qty_total`/`qty_reserved` без `ensureAvailable` под локом, → порча станет невидимой (ни exception, ни constraint violation, ни падение теста на sqlite).

## Корневая причина (гипотеза)
Расчёт на семантику `unsignedBigInteger`, которой в Postgres нет; единственная линия обороны — код, дублируемый в каждом пути декремента.

## Радиус поражения
Все балансы inventory. Latent — пока все текущие пути guard'ятся, не проявляется; это defense-in-depth gap, повышающий цену любой будущей ошибки.

## Направление фикса (1-2 строки, НЕ реализовано)
Отдельной миграцией добавить CHECK `qty_total >= 0 AND qty_reserved >= 0 AND qty_reserved <= qty_total`.
