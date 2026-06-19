---
id: F-0078
flow: products-catalog
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---

## Симптом
Массовая привязка/отвязка агентов к точкам продукта (`addProductPointAgents`/`deleteProductPointAgents`) крутит Core-write в двойном цикле без try/catch и без агрегации, а затем рапортует жёстко зашитые счётчики `attached_count = target_pairs` / `skipped_count = 0` (и симметрично для delete). Счётчики и история не отражают реальность; при частичном сбое — 500 с частичной записью в Core без компенсации.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Project/PointController.php:746-754` — двойной `foreach ($pointIds as $pointId){ foreach ($userIds as $userId){ $pointService->addAgent($agent); }}` без try/catch и без сбора результата.
- `…/PointController.php:756-757` — `$attachedCount = $targetPairs; $skippedCount = 0;` (константы, не подсчёт факта).
- `…/PointController.php:762-767` — эти же константы пишутся в `History` как «Добавлено связей … пропущено …».
- `deleteProductPointAgents` (`…/PointController.php` ~836-872) — симметрично: `$detachedCount = $targetPairs`, а `deleteAgent`→`coreEndAssignment` для отсутствующей привязки — no-op, т.е. реально отвязанных может быть меньше.
- `PointService::addAgent` бросает `RuntimeException`/`CoreApiException`/`InvalidArgumentException` при отсутствии `core_location_external_id`/membership.

## Триггер / repro
1. **Лживый счётчик (happy-path):** часть пар (точка×агент) уже привязана → `addAgent` идемпотентно no-op, но в ответе всё равно `attached_count = target_pairs` (повторные привязки засчитаны как новые). Симметрично `detached_count` для delete.
2. **Частичный сбой:** одна из точек без `core_location_external_id` → исключение на середине цикла → 500. Пары до неё уже записаны в Core, отката нет, `History` не пишется. Оператор не знает, что прошло.

## Корневая причина (гипотеза)
Счётчики не вычисляются из фактических результатов per-pair; цикл по сетевым Core-операциям без изоляции сбоя одной пары. **Новый инстанс класса F-0010** (нетранзакционный bulk + фейковые счётчики), но на Core-gateway пути (пост-D4/D5), а не на старом `project_point_agents` pivot. Снижено с P1 (так оценил субагент) до P2: идемпотентность `addAgent` (no-op на уже привязанных) делает частичную запись self-healing при retry, поэтому это инаккуратность отчёта + аудита, а не порча данных.

## Радиус поражения
Массовая привязка агентов к продукту по всем точкам (admin / point.management). Неверная история, частичная запись в Core при сбое, ложные счётчики в ответе.

## Направление фикса
Агрегировать реальные success/skip/fail per-pair с try/catch вокруг `addAgent`/`deleteAgent`; возвращать честные счётчики + список упавших пар; History писать по факту. См. также F-0010.
