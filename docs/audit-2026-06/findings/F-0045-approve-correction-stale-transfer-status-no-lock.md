---
id: F-0045
flow: inventory-requests-approvals
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---
## Симптом
`approveRequest`/`rejectRequest` заявки на корректировку передачи проверяют статус самой передачи на stale, не залоченной eager-loaded модели, прочитанной до транзакции. Внутри транзакции под `lockForUpdate` пере-проверяется только статус заявки, но не статус передачи → заявка может перейти в `approved` поверх уже изменившейся передачи.

## Доказательства (file:line)
- `app/Services/Inventory/InventoryTransferCorrectionRequestService.php:315-318` (approve) и `:372-375` (reject) — `$transfer = $correctionRequest->transfer; if ($transfer->status === ACCEPTED) …` читается из eager-loaded relation **вне** `DB::transaction`.
- Внутри транзакции (`:320-338` reject / `:377-395` approve) передача не блокируется и её статус не пере-проверяется — только `$correctionRequest->status !== PENDING`.
- Контраст: `executeCorrection` (`:472-499`) залочивает передачу `lockForUpdate` и пере-проверяет её статус (ACCEPTED/CANCELLED) внутри транзакции — то есть правильный паттерн в сервисе есть, но в approve/reject не применён.

## Триггер / repro
Менеджер открыл карточку заявки на корректировку; параллельно передача акцептуется (accept → `runFinalizeTransfer`) или отменяется. Менеджер жмёт approve: pre-check видел старый статус передачи, внутри транзакции статус передачи не сверяется → заявка переходит в `approved` для передачи в несовместимом статусе.

## Корневая причина (гипотеза)
Re-check под локом охватывает только entity заявки, не агрегат «передача». Проверка статуса передачи идёт по stale relation вне атомарного контекста.

## Радиус поражения
Заявка на корректировку в `approved` для уже принятой/отменённой передачи. Прямой порчи балансов нет (`executeCorrection` позже отвалится на проверке статуса передачи), но образуется «approved, но неисполнимый» хвост и рассинхрон состояния очереди заявок. Проявляется при конкурентности.

## Направление фикса (1-2 строки, НЕ реализовано)
Внутри транзакций approve/reject залочить передачу (`lockForUpdate`) и пере-проверить её статус, как уже сделано в `executeCorrection`.
