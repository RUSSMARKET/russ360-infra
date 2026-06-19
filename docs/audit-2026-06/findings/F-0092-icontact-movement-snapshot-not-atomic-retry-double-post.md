---
id: F-0092
flow: icontact-sync
dimension: data-integrity
severity: P1
confidence: likely
services: [rusaisklad_back]
status: open
---

## Симптом
Идемпотентность применения продаж iContact держится на `IContactSourceSnapshot.last_applied_qty` (delta = currentQty − last_applied_qty), но обновление снапшота и складское движение НЕ в одной транзакции. `InventoryService.issue` открывает собственную транзакцию и коммитит движение; `last_applied_qty` пишется отдельным save после. Краш между ними → движение проведено, маркер не сдвинут → retry повторно списывает то же количество.

## Доказательства (file:line)
- `rusaisklad_back/app/Services/Inventory/IContactSyncTaskProcessorService.php:274-325` — `issue(...)` (своя tx) коммитит, затем per-item `snapshot->forceFill(['last_applied_qty'=>...])->save()` вне неё.
- `app/Domain/Inventory/Services/IContactDeltaService.php:13-44` — delta строго против `last_applied_qty`.
- `InventoryService.php:1071-1143` — `issue` без idempotency-key; всегда `InventoryMovement::create`.

## Триггер / repro
Краш воркера / ошибка БД между commit `issue` и save снапшота → движение проведено, `last_applied_qty` не продвинут. При retry (`retryTask`/`retryRun` пере-парсит тот же отчёт) delta пересчитывается против устаревшего `last_applied_qty` → повторное списание того же количества (двойной decrement остатка).

## Корневая причина (гипотеза)
Нет атомарной связи внешнего эффекта (движение) и маркера идемпотентности (снапшот); `issue` не имеет dedup/idempotency-key по `source_item_ids`.

## Радиус поражения
Складские балансы любого проекта с iContact-синком при retry; тихий over/under-issue.

## Направление фикса
Передавать idempotency-key (хеш `sync_task_id`+группа) в `issue` с уникальностью на meta движения, ЛИБО обновлять `last_applied_qty` в одной транзакции с движением (обернуть per-group apply в один `DB::transaction`, вызывающий no-own-tx вариант issue).
