---
id: F-0101
flow: results-reporting
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`GET /api/staff/{user_id}/result` (`getAgentResult`) не применяет reporting-scope: РГ/РП/регионал могут читать дневные результаты ЛЮБОГО агента по id, вне своей зоны видимости. Соседние эндпоинты семейства (`getStaffResult`, `getTotalResults`) scope применяют — несогласованность.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Staff/PlansController.php:1043-1080` — после валидации сразу `User::where('role_id', AGENT)->where('id',$user_id)` → `shifts()->dateFact()`, без `resolveReportingScope`/`hasAccessToUser`/сверки `scope['agent_ids']`.
- Контраст: `getStaffResult` (`:699-705`) и `getTotalResults` (`:1217-1237`) используют reporting-scope.
- `rusaifin/routes/api.php:223` — гейт только `CheckPermission:staff.management` (этим правом обладают GROUP_LEADER/REGIONAL_DIRECTOR).

## Триггер / repro
РГ (GROUP_LEADER) → `GET /api/staff/{любой_user_id}/result?date=5` → 200 с результатами агента вне своей группы.

## Корневая причина (гипотеза)
Эндпоинт не использует единый reporting-scope (инверсия F-0052: не «пусто», а «слишком широко»). Актор — внутренний staff с management-правом → P2.

## Радиус поражения
Все management-роли с ограниченной зоной → чтение результатов агентов вне зоны.

## Направление фикса
После валидации применить `resolveReportingScope(...)` + проверку `in_array($user_id, $scope['agent_ids'])` для непривилегированных (как в `getTotalResults`).
