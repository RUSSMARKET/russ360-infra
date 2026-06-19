---
id: F-0091
flow: sklad-sku-catalog
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом
Удаление SKU из проекта (`deleteFromProject`) удаляет только pivot `project_skus`, оставляя строки `inventory_balances`/`inventory_movements` на тот же глобальный `sku_id`. Эти балансы становятся невидимыми (листинг SKU скоупится `whereHas('projectSkus')`), но продолжают нести ненулевой `qty_total` → фантомные остатки.

## Доказательства (file:line)
- `rusaisklad_back/app/Services/SKU/SKUService.php:113-119` — `deleteFromProject`: `ProjectSku::where(...)->firstOrFail()->delete()` без проверки существующего баланса/движения.
- `database/migrations/2024_01_15_000007_create_skus_table.php:32` — `project_skus.sku_id` FK `onDelete('cascade')`, НО `inventory_balances.sku_id` (`2026_02_06_000001:19`) ссылается на глобальную `skus`, не на `project_skus` → удаление pivot не каскадит в балансы.
- `rusaisklad_back/app/Models/SKU.php:113-126` (`scopeInProject`) — видимость в проекте держится на pivot.

## Триггер / repro
Промоутер держит остаток SKU X в проекте P → админ `DELETE /skus/{X}` для P → строка баланса `(P, holder, X)` остаётся с qty>0, но SKU больше не виден в проекте; повторное добавление SKU (`updateOrCreate` pivot) «воскрешает» устаревший баланс.

## Корневая причина (гипотеза)
Удаление pivot трактуется как логический detach без проверки нулевого остатка / архивации балансов. Класс orphan (родственно F-0002) на складских остатках.

## Радиус поражения
Поучётный остаток по проекту; фантомные балансы, дрейф аудита при повторном добавлении SKU.

## Направление фикса
В `deleteFromProject` блокировать удаление (или soft-деактивировать pivot) при наличии ненулевого `inventory_balances` для `(project, sku)`; повторить guard-паттерн `deleteIfEmpty`, уже применённый к категориям.
