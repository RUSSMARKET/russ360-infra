---
id: F-0010
flow: point-agent-binding
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Массовые `addProductPointAgents` / `deleteProductPointAgents` не атомарны и неверно рапортуют результат: при исключении в середине цикла часть пар уже записана в Core, но эндпоинт отдаёт 500; при штатной отработке `attached_count`/`detached_count` ставится равным `targetPairs` безусловно (фиктивный отчёт).

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Project/PointController.php:746-757` — цикл `addAgent` без try/catch; `$attachedCount = $targetPairs; $skippedCount = 0;` проставляются вне зависимости от факта.
- `PointService.php:226-243 addAgent` может бросить `\RuntimeException`/`\InvalidArgumentException` (нет membership/Core-employee, нет `core_location_external_id`) → 500, прерывая цикл с уже закоммиченными в Core привязками предыдущих пар.
- Delete-ветка `PointController.php:820-850` — аналогично.

## Триггер / repro
Продукт на 50 точках, среди агентов один без Core-membership/linked-employee → на N-й паре throw → пары 1..N-1 уже привязаны в Core, ответ 500. Оператор повторяет → ещё привязки (идемпотентность спасает от дублей, но `attached_count`/`points_count` всё равно фиктивны).

## Корневая причина (гипотеза)
Счётчики захардкожены под семантику «всё или ничего», тогда как фактическая семантика — best-effort построчно, без агрегирования реального результата и без отката.

## Радиус поражения
Операторские отчёты о массовой привязке недостоверны; при частичном сбое UI показывает 500, хотя часть работы выполнена → оператор не знает реального состояния.

## Направление фикса (1-2 строки, НЕ реализовано)
Считать факт по результату каждого `addAgent`/`deleteAgent`, ловить per-pair ошибки, возвращать реальные attached/skipped/failed.
