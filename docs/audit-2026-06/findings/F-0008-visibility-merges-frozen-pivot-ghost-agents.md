---
id: F-0008
flow: point-agent-binding
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
«Призрачные» агенты в видимости персонала: агент, отвязанный от точки ПОСЛЕ cutover, остаётся видимым в одном пути (`StaffVisibilityScopeService`), но не в параллельном (`StaffService`). Разные списки персонала на разных экранах для одного агента; со временем накапливается.

## Доказательства (file:line)
- `rusaifin/app/Services/Staff/StaffVisibilityScopeService.php:661-666` + `:672-685` — `legacyAgentUserIdsForLocalPointIds` читает frozen `project_point_agents` и МЕРЖИТ с Core-результатом.
- Контраст: `rusaifin/app/Services/Staff/StaffService.php:286-291` — тот же смысловой запрос «агенты в проекте» берётся через `memberUserIdsForLocalPointIds(..., ['agent'])` БЕЗ legacy-пивота.
- `PointService.php:249-256` — `deleteAgent` Core-only; frozen-пивот `project_point_agents` при откреплении НЕ чистится (D5, read-only).

## Связь с known-issue
Аудит 2026-05-18 знает про dual-read `StaffVisibilityScopeService` (Core+legacy SQL) и понизил до P2, посчитав, что legacy-ветка читает «legacy-специфичные данные без drift-риска». НОВОЕ здесь: конкретный пост-cutover механизм drift — Core-detach не чистит замороженный пивот, поэтому merge даёт stale-видимость, и это расходится со вторым Core-only путём (`StaffService`). Drift-риск реализуется, а не гипотетичен.

## Триггер / repro
Открепить агента от точки после cutover (Core-assignment `ended`, строка в `project_point_agents` осталась) → `agentUserIdsForLocalPointIds` всё ещё вернёт его как видимого; путь `StaffService` — нет.

## Корневая причина (гипотеза)
Незавершённый reader-switch: одна ветка дочитывает «для совместимости» замороженный пивот, который пост-cutover write-path не поддерживает.

## Радиус поражения
Видимость персонала (visibility scope) для support/RG/PM — «призрачные» агенты на точках после открепления.

## Направление фикса (1-2 строки, НЕ реализовано)
Убрать `legacyAgentUserIdsForLocalPointIds` из merge (Core — единственный источник истины), приведя к поведению `StaffService`; либо явно обосновать расхождение.
