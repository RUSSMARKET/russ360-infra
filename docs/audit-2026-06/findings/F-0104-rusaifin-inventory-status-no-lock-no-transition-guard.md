---
id: F-0104
flow: rusaifin-inventory-agent
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Статус weekly/supply-заявки можно перевести в любое enum-значение в любом направлении (closed→pending_review, approved→pending_review), теряя семантику `*_at`-таймстемпов; два параллельных ревьюера затирают друг друга (lost update). Read-then-write без lock/транзакции и без матрицы переходов.

## Доказательства (file:line)
- `rusaifin/app/Services/Inventory/InventoryService.php:178-220` (`updateWeeklyStatus`) и `:222-268` (`updateSupplyStatus`) — читают `$inventory->status`, присваивают новый, `save()` без `lockForUpdate`/транзакции/re-check.
- `rusaifin/app/Http/Requests/.../UpdateWeeklyInventoryStatusRequest.php:24-32` — допускает любое enum-значение, без матрицы допустимых переходов.
- Таймстемпы (`approved_at`/`shipped_at`/`closed_at`) выставляются «вперёд», но не сбрасываются при откате назад.

## Триггер / repro
Две параллельные `POST .../status` (viewed и closed) на одну заявку → недетерминированный итог + рассогласованные `*_at`. Либо одиночный `closed→pending_review` оживляет закрытую заявку с заполненным `closed_at`.

## Корневая причина (гипотеза)
Нет transition-guard и нет пессимистичной блокировки/транзакции. Класс F-0001.

## Радиус поражения
weekly + supply, все ревьюер-роли; корректность аудит-таймстемпов и согласованность статуса.

## Направление фикса
Матрица допустимых переходов в валидаторе/сервисе + `DB::transaction` с `lockForUpdate` и re-check текущего статуса.
