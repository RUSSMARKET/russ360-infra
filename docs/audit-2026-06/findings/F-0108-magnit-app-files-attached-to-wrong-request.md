---
id: F-0108
flow: requests-cards-magnit
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
При выдаче «Магнит Подписка» + галка приложения файлы повторно грузятся на ИСХОДНУЮ заявку (`productHistory`), а не на созданную «Магнит Приложение» (`magnitProductHistory`): новая заявка остаётся без фото, на исходной — дубли файлов.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Product/RequestController.php:597` — создаётся `$magnitProductHistory`.
- `…/RequestController.php:609-660` — блок загрузки файлов использует `$productHistory->id` (`:610, 627, 652`) вместо `$magnitProductHistory->id`. `setField` для card_number/issued (`:599-608`) корректно идёт на новую заявку, файлы — нет.

## Триггер / repro
Агент выдаёт «Магнит Подписку» с файлами и `mobile_app_with_subscription_to_magnit=1` → файлы дублируются на подписку, у заявки-приложения 0 файлов.

## Корневая причина (гипотеза)
Copy-paste блока загрузки без замены id заявки.

## Радиус поражения
Заявки «Магнит Приложение» и их комплектность фото; косвенно приёмка/оплата по этим заявкам.

## Направление фикса
Во вложенном блоке использовать `$magnitProductHistory->id` (или `new RequestService($magnitProductHistory->id)` + единый хелпер загрузки).
