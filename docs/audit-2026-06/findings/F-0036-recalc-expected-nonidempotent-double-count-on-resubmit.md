---
id: F-0036
flow: inventory-check
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaisklad_back]
status: open
---
## Симптом
Повторная отправка строки инвентаризации после отклонения менеджером удваивает поправку `qty_expected`: дельта движений за период применяется к уже-скорректированному ожидаемому значению ещё раз. Итог — завышенное/заниженное `qty_expected` → ложные расхождения → неверные `CORRECTION`-движения и порча реальных балансов при `apply-corrections`.

## Доказательства (file:line)
- `app/Services/Inventory/InventoryCheckService.php:405-440` — `recalculateExpectedAtSubmit()` считает дельту POSTED-движений за период (`created_at > check.created_at`) и на `:440` **мутирует на месте**: `$item->update(['qty_expected' => max(0, $item->qty_expected + $delta)])`. Не идемпотентно: читает уже изменённое `qty_expected` и снова прибавляет.
- `:135-159` — `submitLine()` допускает отправку при `line->status === PENDING` (`:137`) и каждый раз вызывает `recalculateExpectedAtSubmit` (`:159`).
- `:216-229` — `rejectCheck()` сбрасывает строки в `PENDING` + `submitted_at = null` (`:224-228`), но **не восстанавливает** `qty_expected` к снапшоту.
- `:114-128` — `updateLineItems()` правит только `qty_actual`/`comment`, `qty_expected` не трогает; ре-снапшота при resubmit нет.
- Снапшот `qty_expected` ставится один раз при создании на `:393` (`= balance->qty_total`).

## Триггер / repro
Инвентаризация идёт по диапазону дат `period_start..period_end`; в течение периода неизбежно происходят POSTED-движения. 1) Супервайзер заполняет и отправляет строку → `submitLine` пересчитывает `qty_expected = snapshot + delta`, сохраняет. 2) Менеджер отклоняет (`reject`) → строка снова `PENDING`, `qty_expected` остаётся `snapshot + delta`. 3) Супервайзер правит факт и повторно отправляет → `submitLine` снова добавляет ту же дельту: `qty_expected = snapshot + 2·delta`. 4) Approve + apply-corrections применяют корректировку по искажённому ожидаемому → реальный баланс выставлен неверно на величину `delta`.

## Корневая причина (гипотеза)
Неидемпотентный in-place пересчёт `qty_expected` в `recalculateExpectedAtSubmit` в сочетании с тем, что `rejectCheck` не восстанавливает снапшотное `qty_expected`. Пересчёт ведётся от фиксированного `check.created_at` без хранения «что уже учтено».

## Радиус поражения
Все инвентаризации, прошедшие цикл `reject → resubmit` при наличии любых движений в периоде (т.е. практически любые многодневные проверки с движениями). Искажение `qty_expected` → ошибочные `CORRECTION`-движения → порча `inventory_balances.qty_total` при `apply-corrections`. Детерминированно, гонка не нужна.

## Направление фикса (1-2 строки, НЕ реализовано)
Пересчитывать `qty_expected` от неизменного снапшота (хранить `qty_expected_snapshot` отдельно и вычислять `snapshot + delta`), либо в `rejectCheck` восстанавливать `qty_expected` к снапшоту перед повторной отправкой.
