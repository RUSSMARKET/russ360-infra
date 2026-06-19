---
id: F-0055
flow: staff-visibility
dimension: data-integrity
severity: P2
confidence: needs-verification
services: [rusaifin]
status: open
---
## Симптом
При двух локальных users с одинаковым `core_employee_external_id` резолв области видимости silently теряет одного из них (схлопывание по ключу).

## Доказательства (file:line)
- `database/migrations/2026_04_16_120000_add_core_employee_external_id_to_users_table.php:15` — колонка с `->index()`, НЕ unique. Дубли структурно возможны.
- `app/Domain/Core/Support/CoreScopeResolver.php:174-176` — `User::query()->whereIn('core_employee_external_id', $missing)->pluck('id', 'core_employee_external_id')` — ключ по external_id схлопывает дубли, остаётся один id (последний). Метод `localUserIdsByEmployeeExternalIds` используется во всём резолве видимости.
- Контекст: задокументированные регрессии orphan/duplicate registration (memory: registration_duplicate_on_signing, orphan users) показывают, что дубли в проде реально появляются.

## Триггер / repro
Два user-записи с одним `core_employee_external_id` (дубль приёма на работу) → в staff-листинге/видимости показывается только один. Требует проверки наличия дублей в проде: `SELECT core_employee_external_id, COUNT(*) FROM users WHERE core_employee_external_id IS NOT NULL GROUP BY 1 HAVING COUNT(*)>1`.

## Корневая причина (гипотеза)
Отсутствие UNIQUE на `core_employee_external_id` + `pluck('id', external_id)` теряет дубли при схлопывании по ключу.

## Радиус поражения
Все методы видимости через `localUserIdsByEmployeeExternalIds` (resolveVisibleUserIds, ProjectStaffReader::loadUsers, attached/leader/agent резолвы). Зависит от наличия дублей (needs-verification).

## Направление фикса (1-2 строки, НЕ реализовано)
Сначала проверить наличие дублей в проде; добавить UNIQUE (или partial) на `core_employee_external_id`; в резолвере при необходимости группировать в список id, а не схлопывать.
