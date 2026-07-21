---
id: F-0120
flow: requests-cards-magnit
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

Глобальные read-эндпоинты без скоупа зоны: поиск заявки по номеру карты и чтение продукта по id возвращают данные любого проекта (IDOR-чтение метаданных).

## Доказательства (file:line)

- `app/Http/Controllers/Product/RequestController.php:351-372` (`searchCardNumber`, роут `request/card/{card_number}` под одним `auth:oauth`) — `ProductHistoryField::where('field','card_number')->where('value',$n)->get()` → `ProductHistory` по id, БЕЗ agent/project/role-скоупа. Любой авторизованный находит заявку (agent_id/product/point/code/created_at) по номеру карты глобально.
- `app/Http/Controllers/Product/ProductController.php:~107-117` (`getProduct`) — `Product::find($id)` (+`disabled=0` для не-ADMIN), без проектного скоупа: чтение метаданных любого продукта по id.

## Триггер / repro

`GET /api/request/card/<номер>` любым авторизованным → детали чужой заявки. `GET /api/product/<id>` → метаданные любого продукта.

## Корневая причина (гипотеза)

Read-методы не унаследовали продуктово-зональную видимость (паттерн F-0115: визибилити применена лишь в части read-путей).

## Радиус поражения

Чтение метаданных заявок/продуктов вне зоны (PII-минор: agent_id, номер карты-связка). P3.

## Направление фикса (не реализовано)

Скоупить `searchCardNumber` по зоне viewer'а (как `getRequests`); `getProduct` — проверять принадлежность продукта доступному проекту/точке.
