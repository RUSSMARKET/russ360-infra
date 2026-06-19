---
id: F-0001
flow: inventory-transfer
dimension: correctness
severity: P1
confidence: likely
services: [rusaisklad_back]
status: open
---
## Симптом
Передача (`inventory_transfers`) может оказаться в статусе `cancelled`, хотя товар уже физически перенесён на баланс получателя, а резерв отправителя при этом снимается дважды. То есть «отменённая» передача с уже выполненным движением остатков + рассинхрон `qty_reserved` у отправителя (вплоть до ошибочного снятия резерва, принадлежащего другой pending-передаче).

## Доказательства (file:line)
- `app/Services/Inventory/InventoryService.php:498-600` — `cancelTransfer()`: проверка `$transfer->status` в списке `$allowedStatuses` выполняется **до** `DB::transaction` (строки 512-521) на stale-модели из route-model-binding. **Внутри** транзакции (строки 533-597) НЕТ `lockForUpdate()` на строке `inventory_transfers` и НЕТ повторной проверки статуса: на строках 536-573 безусловно делается `qty_reserved -= qty`, на строках 576-578 безусловно ставится `status = CANCELLED` + `save()`.
- `app/Services/Inventory/InventoryService.php:612-685` — `deleteTransfer()`: тот же паттерн (проверка `status === ACCEPTED` на строке 628 вне транзакции, внутри транзакции на строках 641-668 снятие резерва без блокировки/повторной проверки статуса передачи).
- Контраст (доказательство, что это упущение, а не дизайн): `runFinalizeTransfer()` `app/Services/Inventory/InventoryService.php:363` делает `InventoryTransfer::where('id',…)->lockForUpdate()->firstOrFail()` + повторную проверку статуса (369-371); `rollbackTransfer()` `:721` и `updateTransfer()` `:792` тоже блокируют строку `lockForUpdate()`. `acceptTransfer()` `:472-487` оборачивает finalize в транзакцию с блокировкой. Cancel/delete из этого правила выпадают.
- `app/Models/InventoryTransfer.php:18-35` — в модели нет version-колонки / optimistic lock; единственная защита от гонок — пессимистичный `lockForUpdate`, который в cancel/delete не вызывается.

## Триггер / repro
Конкурентные запросы по одной передаче, например:
1. Получатель жмёт «Принять» (`POST /inventory/transfers/{t}/accept`) — в это же время создатель/менеджер жмёт «Отменить» (`POST /inventory/transfers/{t}/cancel`). На sklad-роутах нет idempotency-middleware (есть только в rusaicore), двойной клик не дедуплицируется.
2. `accept` блокирует строку, финализирует: `qty_reserved -= qty`, `qty_total -= qty`, `status = ACCEPTED`, коммит — товар у получателя.
3. `cancel` стартует транзакцию (строку transfer НЕ блокирует), берёт stale-модель со `status = PENDING_ACCEPT`, снимает резерв повторно (если у отправителя остался резерв от других передач — guard `qty_reserved < qty` на строке 564 пройдёт) и перезаписывает `status = CANCELLED`.
Итог: accepted-движение остатков выполнено, но передача помечена cancelled; `qty_reserved` отправителя занижен на лишний `qty`.

Также воспроизводится двойным «Отменить»: при наличии резерва от других передач второй cancel снимет резерв ещё раз.

## Корневая причина (гипотеза)
`cancelTransfer`/`deleteTransfer` не следуют принятому в этом же сервисе паттерну «`lockForUpdate()` строки передачи + повторная проверка статуса внутри транзакции». Проверка статуса идёт по stale-копии из route-model-binding и не атомарна с мутацией балансов и сменой статуса.

## Радиус поражения
Дополнительный racing-путь (выявлен в потоке 13, transfer-documents): финализация передачи через менеджерское `approve` документа (`InventoryDocumentService::approveByManager` → `runFinalizeTransfer`) для проектов с `transfers_require_documents=1` — статус `PENDING_MANAGER_APPROVAL`. Конкурентный `cancelTransfer` против этого пути даёт тот же двойной вычет `qty_reserved` + статус `ACCEPTED`+`CANCELLED` одновременно. Корень и фикс — те же (lock+re-check в cancel/delete). Не отдельная находка.

Только rusaisklad_back, домен Inventory transfers. Затрагивает целостность `inventory_balances.qty_reserved` (учёт зарезервированного товара у отправителей) и согласованность `inventory_transfers.status` с фактическими `inventory_movements`/балансами. Проявляется при конкурентности (двойные клики на мобильном фронте, одновременные действия получателя и менеджера). Не ломает «happy path» одиночных запросов.

## Направление фикса (1-2 строки, НЕ реализовано)
Внутри транзакций `cancelTransfer` и `deleteTransfer` сначала `InventoryTransfer::where('id',$transfer->id)->lockForUpdate()->firstOrFail()` и повторно проверять допустимость статуса (как в `runFinalizeTransfer`), только потом мутировать резервы/статус.
