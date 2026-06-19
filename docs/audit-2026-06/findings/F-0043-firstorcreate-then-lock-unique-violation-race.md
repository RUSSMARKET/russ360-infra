---
id: F-0043
flow: inventory-receipt-warehouse
dimension: correctness
severity: P2
confidence: likely
services: [rusaisklad_back]
status: open
---
## Симптом
Два параллельных первых движения по одной паре `(holder, sku)` (когда строки баланса ещё нет) → один из запросов падает с 500 (unique-violation), его транзакция целиком откатывается. Данные не портятся (нет half-write), но операция теряется до ретрая. Паттерн системный: повторяется в нескольких методах.

## Доказательства (file:line)
- `app/Services/Inventory/InventoryService.php:76-92` — `receipt()`: сначала `InventoryBalance::firstOrCreate([... holder_id=null ...])` БЕЗ блокировки (`:76-87`), затем отдельным запросом `where('id',…)->lockForUpdate()->firstOrFail()` (`:90-92`). Между `first` и `create` внутри `firstOrCreate` есть окно гонки.
- `database/migrations/2026_02_06_000001_create_inventory_balances_table.php` — уникальный индекс `(project_id, holder_type, holder_id, sku_id)` превращает гонку в `QueryException` (500).
- Тот же паттерн `firstOrCreate`→`lockForUpdate` в `runFinalizeTransfer` (to-balance) и в `balanceForUpdate` (~`:1788-1803`).

## Триггер / repro
Первое в истории движение SKU X на склад (или первое зачисление пользователю) выполняется параллельно двумя запросами (два менеджера, либо `allocate`+`receipt` нового SKU одновременно) до того, как строка баланса создана. Один из них получает unique-violation → 500; пользователь вынужден повторить.

## Корневая причина (гипотеза)
`firstOrCreate` не атомарен с последующим `lockForUpdate`; создание строки баланса не сериализуется блокировкой, а опирается на падение по unique-индексу без обработки.

## Радиус поражения
Краевой — только первое появление пары `holder×sku`. Без потери целостности (одна транзакция откатывается целиком), но даёт пользовательский 500 и срыв операции. Системность (несколько методов) повышает частоту.

## Направление фикса (1-2 строки, НЕ реализовано)
`INSERT ... ON CONFLICT DO NOTHING` (upsert) с последующим `lockForUpdate`, либо обёртка-ретрай на unique-violation в одном helper'е для всех путей.
