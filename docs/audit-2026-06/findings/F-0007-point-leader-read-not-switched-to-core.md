---
id: F-0007
flow: point-agent-binding
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
`getProjectPoint` и `getProjectPoints` возвращают `leader: null` для всех точек, тронутых после cutover, хотя РГ реально назначен. Для старых точек возможен показ УСТАРЕВШЕГО лидера (если РГ потом сменили через Core).

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Project/PointController.php:144-146` — `$point->...->get([... 'leader:id,name,surname,patronymic,email,phone'])`; список `ProjectService.php:98-99` — `->with('leader:...')`.
- `app/Models/Project/Point.php:55-56` — `leader()` = `belongsTo(User::class, 'group_leader_id')`.
- `PointController.php:307-309` — при update `group_leader_id` ЯВНО снимается из `$validated` (`unset`), комментарий «group_leader_id is Core-authoritative (D4/D5) — set via setGroupLeader, not the frozen column».
- `PointService.php:191-219` — `setGroupLeader` пишет только в Core, локальную колонку не трогает; grep подтвердил — ни один live-путь больше не пишет `project_points.group_leader_id`.
- Грепом не найдено Core-гидрации лидера в read-пути PointController/ProjectService (в отличие от агентов, которые подтягиваются через `PointAgentReader::attachAgents` в `getPointAgents`).

## Триггер / repro
Создать/обновить точку после cutover → назначить РГ → `GET project/{id}/point/{point_id}` → поле `leader` пустое (frozen `group_leader_id` = NULL).

## Корневая причина (гипотеза)
Write-path РГ переключён на Core (D5 freeze колонки), а read-path точки (одиночный и список) остался на frozen `leader()`-связи. Reader-switch сделали для shift/plan (2026-05-29), но НЕ для самого PointController/ProjectService.

## Радиус поражения
Весь UI точек проекта (карточка + список): РГ не отображается для post-cutover точек; для старых — риск устаревшего значения.

## Направление фикса (1-2 строки, НЕ реализовано)
Читать лидера из Core (нужен прямой `leaderForPoint(locationExternalId)`; обратное направление `PointAgentReader::leaderPointForEmployee` уже есть), по аналогии с тем, как `agents` уже читаются через `PointAgentReader::attachAgents`.
