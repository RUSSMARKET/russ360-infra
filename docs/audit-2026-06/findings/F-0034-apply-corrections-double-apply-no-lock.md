---
id: F-0034
flow: inventory-check
dimension: data-integrity
severity: P1
confidence: likely
services: [rusaisklad_back]
status: open
---
## Симптом
Два конкурентных вызова `apply-corrections` для одной инвентаризации оба проходят проверку статуса и оба применяют корректировки к балансам → `qty_total` держателей сдвигается дважды, создаётся двойной комплект `CORRECTION`-движений. «Применённая» инвентаризация на самом деле применена два раза.

## Доказательства (file:line)
- `app/Services/Inventory/InventoryCheckService.php:238-242` — `applyCorrections()` проверяет `$check->status !== APPROVED` на route-model-bound stale-модели **до** `DB::transaction`.
- `:265` — транзакция открывается только здесь; внутри (`:265-309`) сам `$check` **не перечитывается** с `lockForUpdate` (заблокирован только `InventoryBalance` на `:274`).
- `:303-306` — статус ставится `CORRECTIONS_APPLIED` без повторной проверки исходного статуса внутри транзакции.
- Контраст (доказательство, что это упущение): `app/Services/Inventory/InventoryService.php:363` `runFinalizeTransfer` делает `InventoryTransfer::where('id',…)->lockForUpdate()->firstOrFail()` + повторную проверку статуса (`:369`) внутри транзакции.

## Триггер / repro
Менеджер дважды быстро жмёт «применить корректировки» (двойной клик / retry на таймауте). Оба HTTP-запроса грузят свой `$check` со `status=APPROVED` через route-model-binding, оба проходят guard на `:238`. T1 блокирует балансы, применяет дельты, коммитит, ставит `CORRECTIONS_APPLIED`. T2 ждёт лок баланса на `:274`, после коммита T1 берёт уже сдвинутый баланс и применяет ту же дельту (`$discrepancyItems` со статическими `qty_actual`/`qty_expected` посчитаны на `:245`, до транзакции) ещё раз. Последовательный повтор (после полного коммита T1) безопасен — свежий `$check` уже `CORRECTIONS_APPLIED`; ломается только конкурентность.

## Корневая причина (гипотеза)
State-guard на stale route-bound модели без pessimistic lock и без re-check статуса внутри транзакции (тот же класс дефекта, что F-0001). Переход в `CORRECTIONS_APPLIED` не служит атомарным идемпотентным барьером, т.к. проверяется не он.

## Радиус поражения
`inventory_balances.qty_total` всех держателей с расхождениями в данной инвентаризации; дублирующиеся `CORRECTION`-движения; искажение учётных остатков проекта. Проявляется только при конкурентности (двойной клик на мобильном фронте).

## Направление фикса (1-2 строки, НЕ реализовано)
Внутри `DB::transaction` перечитать `InventoryCheck::where('id',$check->id)->lockForUpdate()->firstOrFail()` и повторно проверить `status === APPROVED` перед мутацией балансов (как в `runFinalizeTransfer`); переход в `CORRECTIONS_APPLIED` под локом станет идемпотентным барьером.

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`InventoryCheckService:238` проверяет статус на stale-модели до транзакции (:265); внутри блокируется только `InventoryBalance`, сам `InventoryCheck` под локом не перечитывается.
