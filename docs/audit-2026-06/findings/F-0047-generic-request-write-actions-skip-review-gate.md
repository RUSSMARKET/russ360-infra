---
id: F-0047
flow: inventory-requests-approvals
dimension: architecture-drift
severity: P3
confidence: confirmed
services: [rusaisklad_back]
status: open
---
## Симптом
В дженерик-контроллере заявок read-пути (`index`/`show`) проверяют Gate `reviewInventoryRequests`, а мутирующие `approve`/`reject`/`cancel`/`execute` проверяют только `view` — авторизация ролей для записи целиком делегирована в сервисы. Функциональной дыры нет (сервисы прикрывают), но gate-проверки между read и write путями непоследовательны.

## Доказательства (file:line)
- `app/Http/Controllers/API/Inventory/InventoryRequestController.php:77-83, 125-131` — `index`/`show` проверяют и `view`, и `reviewInventoryRequests`.
- `:185-187, 244-245, 287-289, 357-359` — `approve`/`reject`/`cancel`/`execute` проверяют только `view`.
- Прикрытие в сервисах: `InventoryTransferCorrectionRequestService.php:299-302, 356-359, 465-468` (`getProjectRole ∈ [admin,manager]`); `InventoryWriteoffRequestService.php:~139, ~217` (аналогично); `cancel` — by-creator.
- Обход через произвольный `{requestType}` НЕ возможен: `in_array($requestType, InventoryRequestType::all())` + `match` с `default => Forbidden` (подтверждено трассировкой всех веток).

## Триггер / repro
Реального обхода авторизации нет (защита в сервисном слое). Дефект — несогласованность: новый тип заявки/новый сервисный путь, добавленный без дублирующей ролевой проверки внутри, останется без gate на write-пути контроллера.

## Корневая причина (гипотеза)
Авторизация размазана между Gate (read) и сервисом (write); единый паттерн «gate на write» не выдержан.

## Радиус поражения
Ремонтопригодность/консистентность авторизации. Функциональной дыры на текущем коде нет.

## Направление фикса (1-2 строки, НЕ реализовано)
Продублировать `reviewInventoryRequests`-gate в write-экшенах контроллера для единообразия, либо явно задокументировать, что ролевая проверка — ответственность сервисов.
