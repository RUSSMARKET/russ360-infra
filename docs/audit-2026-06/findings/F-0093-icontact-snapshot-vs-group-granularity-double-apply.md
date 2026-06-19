---
id: F-0093
flow: icontact-sync
dimension: correctness
severity: P2
confidence: needs-verification
services: [rusaisklad_back]
status: open
---

## Симптом
`applyDeltas` группирует по `mapped_user_id|mapped_sku_id|occurred_at`, но снапшот keyed по `account|activity|session_id|source_sku_name` (без `occurred_at`). Две source-строки с тем же session+source-SKU, но разным `occurred_at`, маппятся в ОДИН снапшот, но попадают в РАЗНЫЕ apply-группы → обе считают delta против одного `last_applied_qty` → обе списывают, затем обе перезаписывают `last_applied_qty=qty`.

## Доказательства (file:line)
- `rusaisklad_back/app/Services/Inventory/IContactSyncTaskProcessorService.php:263-267` — ключ группы.
- `…:549-552` — ключ снапшота (без `occurred_at`).
- `…:214-243` — `calculateDeltas` считает delta per source-item ДО любого apply; `last_applied_qty` продвигается только post-issue (`:319-324`).

## Триггер / repro
Отчёт portfolio содержит один `session_id`+`source_sku_name` дважды с разными метками времени → количество применяется дважды (over-issue).

## Корневая причина (гипотеза)
Гранулярность снапшота (session+sku) грубее гранулярности apply (session+sku+occurred_at); baseline delta не перечитывается между группами.

## Радиус поражения
Over-issue для отчётов с внутрисессионными дубль-SKU-строками. Требует верификации: может ли парсер `IContactPortfolioReportParser` эмитить такие дубли (если дедупит по session+sku — impact нулевой).

## Направление фикса
Включить `occurred_at` в ключ снапшота, либо агрегировать все строки одного snapshot-ключа перед delta/apply.
