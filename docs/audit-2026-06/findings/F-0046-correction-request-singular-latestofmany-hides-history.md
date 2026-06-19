---
id: F-0046
flow: inventory-requests-approvals
dimension: correctness
severity: P3
confidence: likely
services: [rusaisklad_back]
status: open
---
## Симптом
После того как сняли UNIQUE и разрешили несколько заявок на корректировку одной передачи, связь `InventoryTransfer::correctionRequest()` (singular, `latestOfMany`) показывает только самую новую заявку. В очереди заявок и в execute-ресурсе грузится именно singular-связь → предыдущие approved/rejected заявки скрыты от оператора.

## Доказательства (file:line)
- `app/Models/InventoryTransfer.php:111-114` — `correctionRequest()` = `hasOne(...)->latestOfMany('id')`.
- `database/migrations/2026_03_02_120000_allow_multiple_correction_requests_per_transfer.php` — снимает `unique(['transfer_id'])`, разрешая несколько заявок на передачу.
- `app/Services/Inventory/InventoryRequestInboxService.php:~144` — очередь `transfer_approval` грузит `correctionRequest.requestedBy…` (singular) при том, что заявок теперь может быть много.
- `app/Http/Controllers/API/Inventory/InventoryTransferCorrectionRequestController.php:~615` — execute-ресурс также читает singular-связь.

## Триггер / repro
1-я заявка на корректировку rejected, создана 2-я. В карточке/ресурсе передачи отображается только 2-я; история (1-я) доступна лишь через `correctionRequests()` (plural), который в этих местах не грузится.

## Корневая причина (гипотеза)
Singular-связь оставлена ради обратной совместимости после перехода на множественные заявки; места отображения не переведены на plural.

## Радиус поражения
Полнота отображения «текущей» заявки и истории. Данные не портятся; вопрос наблюдаемости/контракта ответа API.

## Направление фикса (1-2 строки, НЕ реализовано)
Где нужна история — грузить `correctionRequests` (plural); singular осознанно оставить как «текущую».
