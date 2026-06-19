---
id: F-0044
flow: inventory-receipt-warehouse
dimension: correctness
severity: P3
confidence: likely
services: [rusaisklad_back]
status: open
---
## Симптом
Бизнес-инвариант «распределение со склада только на supervisor» проверяется лишь при создании allocate-передачи. Если у получателя после создания изменилась роль/членство (понижен до promoter, исключён из проекта), `acceptTransfer` всё равно финализирует и зачислит склад→этому юзеру без повторной валидации роли.

## Доказательства (file:line)
- `app/Services/Inventory/InventoryService.php:~1864-1867` — `allocateFromWarehouse`: роль получателя (`supervisor`) проверяется только на создании.
- `:472-487` — `acceptTransfer`: проверяет статус передачи и `isRecipient` (по `to_user_id`, `:478`), но НЕ роль/членство получателя.
- `:361-466` — `runFinalizeTransfer`: для `from_warehouse` не перепроверяет роль/членство `to_user`, только статус передачи.
- Членство держится в Core и может измениться вне sklad (TOCTOU между create и accept).

## Триггер / repro
Allocate на supervisor S → S понижен/удалён из проекта (изменение Core membership) → S (или admin) жмёт accept → склад списан, остаток зачислен юзеру без валидной supervisor-роли.

## Корневая причина (гипотеза)
Ролевой инвариант валидируется на этапе создания, а исполнение баланса — на accept без повторной проверки; membership протухает между шагами.

## Радиус поражения
Редкий. Даёт «висящий» остаток у юзера без валидной проектной роли — не виден в ролевых фильтрах `listBalances`, искажает учёт.

## Направление фикса (1-2 строки, НЕ реализовано)
В `runFinalizeTransfer` для `from_warehouse` перепроверять, что `to_user` всё ещё supervisor и состоит в проекте (через `ProjectMembershipProvider`).
