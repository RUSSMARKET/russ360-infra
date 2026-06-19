---
id: F-0081
flow: products-catalog
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Два из трёх system-эндпоинтов разнесения продуктов по точкам (`add-product-to-points`, detach) крутят `syncWithoutDetaching`/`detach` в цикле БЕЗ `DB::transaction`, инкрементя `points_processed` независимо от факта; третий (`syncProjectProductsToPoints`) уже обёрнут в транзакцию — непоследовательность, частичная запись без отката при сбое на середине.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/System/SystemController.php:168-171` — attach-цикл без транзакции, `$processedPoints++` безусловно.
- `…/SystemController.php:260-263` — detach-цикл без транзакции.
- `…/SystemController.php:309-314` — `syncProjectProductsToPoints` обёрнут в `DB::transaction` (контраст).
- `rusaifin/routes/api.php:489-491` — соответствующие system-роуты.

## Триггер / repro
`GET /api/system/add-product-to-points/...` падает на середине (конкурентный lock / ошибка) → часть точек привязана, ответ не отдан, отката нет. Счётчик `points_processed` мог инкрементиться для непривязанных.

## Корневая причина (гипотеза)
Непоследовательное применение транзакции между тремя родственными system-операциями. Низкий риск: работа идёт по локальной `point_products` (не Core), `syncWithoutDetaching`/`detach` почти идемпотентны, поэтому P3.

## Радиус поражения
Локальная таблица `point_products`; админ-операции синка. Латентно.

## Направление фикса
Обернуть attach/detach-циклы в `DB::transaction` для единообразия с `syncProjectProductsToPoints`.
