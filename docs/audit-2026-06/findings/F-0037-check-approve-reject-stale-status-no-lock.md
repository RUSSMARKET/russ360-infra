---
id: F-0037
flow: inventory-check
dimension: correctness
severity: P2
confidence: likely
services: [rusaisklad_back]
status: open
---
## Симптом
`approveCheck` и `rejectCheck` проверяют статус инвентаризации на route-bound stale-модели без `lockForUpdate` и без повторной проверки внутри транзакции. Конкурентные approve+reject (или двойной approve) одной инвентаризации могут выполниться обоими путями → рассинхрон статуса самой инвентаризации и статусов её строк.

## Доказательства (file:line)
- `app/Services/Inventory/InventoryCheckService.php:187-191` — `approveCheck`: проверка `status !== PENDING_APPROVAL` на переданном `$check`; `DB::transaction` на `:193` не перечитывает `$check` под локом.
- `:210-214` — `rejectCheck`: тот же паттерн; транзакция на `:216` без re-fetch/lock.
- `:200-201` / `:224-228` — внутри транзакций строки массово переводятся в `APPROVED` (approve) либо `PENDING` + `submitted_at=null` (reject).
- Контраст: `app/Services/Inventory/InventoryService.php:363/369` — lock + re-check статуса внутри транзакции.

## Триггер / repro
Два менеджера одновременно: один жмёт «утвердить», другой «отклонить». Оба видят `PENDING_APPROVAL`. Approve ставит `APPROVED` + строки `APPROVED`; затем reject ставит `REJECTED` + строки `PENDING`/`submitted_at=null` (или порядок обратный) → статус инвентаризации и статусы строк рассогласованы (например `REJECTED` при `APPROVED`-строках).

## Корневая причина (гипотеза)
Отсутствие pessimistic lock и повторной проверки статуса внутри транзакции на свежей модели (класс F-0001), на этот раз без прямой порчи балансов — только некорректный переход state-machine.

## Радиус поражения
Согласованность `inventory_checks.status` с `inventory_check_lines.status`. Балансы напрямую не страдают (корректировки применяются отдельным шагом `apply-corrections`, который сам проверяет `APPROVED`). Проявляется только при конкурентности.

## Направление фикса (1-2 строки, НЕ реализовано)
Внутри транзакций `approveCheck`/`rejectCheck` сначала `InventoryCheck::where('id',$check->id)->lockForUpdate()->firstOrFail()` и повторно проверять `PENDING_APPROVAL`.
