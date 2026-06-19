---
id: F-0009
flow: point-agent-binding
dimension: data-integrity
severity: P2
confidence: likely
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Открепление агента может молча не сработать (no-op), оставив открытый Core-assignment, если роль open-assignment'а была мутирована на не-`agent`. Агент «пропадает» из списка точки, но в Core привязка остаётся открытой.

## Доказательства (file:line)
- Инвариант Core: один открытый assignment на `(employee, location)` независимо от роли — partial unique index `ola_employee_location_open_uidx` (`rusaicore/database/migrations/...assignments_table.php:55-59`); `PointService.php:319-333 ensureOpenAssignmentRole` МУТИРУЕТ роль существующей open-записи вместо создания второй.
- Detach: `PointService.php:249-256 deleteAgent` → `coreEndAssignment(userId,'agent')` (`:408-425`) → `CoreOperationalLocationAssignmentGateway.php:67-85 findActiveAssignmentExternalId` фильтрует СТРОГО `((string)$a->role) === 'agent'` (`:79`); при несовпадении → `null` → `coreEndAssignment` тихо выходит (`:416-418`).
- Read: `PointAgentReader::attachAgents` фильтрует `role==='agent'` → агент исчезает из списка точки, хотя assignment в Core открыт.

## Триггер / repro
На точке открыт assignment роли `leader` для сотрудника X; смешанный порядок операций или ручная правка роли в Core оставляет open-запись с ролью ≠ `agent`; `deleteAgent(X)` ищет строго `agent`, не находит → open-assignment остаётся навсегда.

## Корневая причина (гипотеза)
Асимметрия предположений о роли: create-side опирается на «одна запись на пару, роль перетираем», detach-side — на «найти именно agent-запись».

## Радиус поражения
Точечные «неоткрепляемые» агенты; расхождение «список агентов точки» vs «реальные open-assignments в Core».

## Направление фикса (1-2 строки, НЕ реализовано)
Detach должен закрывать open-assignment по паре `(employee, location)` без жёсткого фильтра по роли (как делает create-side), либо fallback при отсутствии role==='agent'.
