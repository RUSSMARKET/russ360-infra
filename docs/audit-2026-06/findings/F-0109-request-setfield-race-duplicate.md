---
id: F-0109
flow: requests-cards-magnit
dimension: data-integrity
severity: P3
confidence: likely
services: [rusaifin]
status: open
---

## Симптом
`setField` — read-then-write без блокировки/уникального индекса: при параллельных вызовах (двойной submit) для одной заявки и одного `field` могут создаться два ряда `product_history_fields` → неоднозначное значение card_number.

## Доказательства (file:line)
- `rusaifin/app/Services/Requests/RequestService.php:24-38` — `where(...)->first()`, при отсутствии `Create(...)`; нет `updateOrCreate` под транзакцией, нет unique(`product_history_id`,`field`).

## Триггер / repro
Двойной submit одной заявки → два ряда поля card_number → неоднозначность.

## Корневая причина (гипотеза)
Read-then-write без атомарности/unique. Класс F-0001/F-0042.

## Радиус поражения
card_number/issued заявок.

## Направление фикса
`updateOrCreate` + unique-индекс на (`product_history_id`, `field`).
