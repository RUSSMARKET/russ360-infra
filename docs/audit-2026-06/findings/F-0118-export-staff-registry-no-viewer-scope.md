---
id: F-0118
flow: staff-visibility
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

`GET /api/staff/registry/export` выгружает реестр ВСЕХ сотрудников (role∈{AGENT,GROUP_LEADER}) по всей системе, фильтруя только опциональными `project`/`point` из запроса и НЕ проверяя, что они в зоне viewer'а. GROUP_LEADER (есть `staff.management`) может выгрузить весь реестр компании или реестр любого чужого проекта.

## Доказательства (file:line)

- `routes/api.php:235` — гейт `CheckPermission:staff.management` (есть у GROUP_LEADER/RD/PM) + `ResolveCurrentProject` (лишь энфорс наличия проекта).
- `app/Http/Controllers/Staff/PlansController@exportStaffRegistry` → `StaffRegistryExport::collection()` (≈:54-111) — тянет всех users по роли, фильтр только по `project`/`point` из запроса; **нет** viewer-zone-скоупа (`resolveVisibleUserIds`/`getAccessiblePointIds`), в отличие от соседних отчётов (`getStaffResult` использует `resolveReportingScope`).

## Триггер / repro

GROUP_LEADER: `GET /api/staff/registry/export` без параметров → XLSX со всеми агентами/РГ системы; либо `?project=<чужой>` → реестр чужого проекта.

## Корневая причина (гипотеза)

Экспорт не унаследовал zone-скоуп reporting-эндпоинтов; доверяет необязательным параметрам запроса без проверки членства.

## Радиус поражения

Массовая утечка PII персонала (ФИО/телефоны/проекты) вне зоны. P2.

## Направление фикса (не реализовано)

Привязать `StaffRegistryExport` к зоне viewer'а (тот же `resolveReportingScope`/`getAccessiblePointIds`, что в остальных отчётах); параметры `project`/`point` валидировать на вхождение в зону.
