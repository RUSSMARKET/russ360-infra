---
id: F-0014
flow: project-support-membership
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Добавление support-менеджера на проект падает с 500 (`RuntimeException`), если у пользователя нет `core_employee_external_id`, вместо понятной доменной ошибки/авто-линковки.

## Доказательства (file:line)
- `rusaifin/app/Services/Project/ProjectService.php:246-257` — `addSupport()` НЕ вызывает `EnsureCoreEmployeeLinked` и сразу зовёт `employeeExternalId($user)`.
- Контраст: `addRegionalDirector()` `:143` и `setRegionalDirectors()` `:214` вызывают `EnsureCoreEmployeeLinked`.
- `ProjectService.php:411-417` — `employeeExternalId()` бросает `RuntimeException`, если `core_employee_external_id` пуст.
- `app/Http/Controllers/Project/ProjectController.php:581` — `setProjectSupport()` зовёт `addSupport()` без try/catch.

## Триггер / repro
Support создан после cutover или попал под orphan-регрессию `setRegistrationRole` (нет Core-employee) → `POST project/{id}/support/add` → 500. РД в том же сценарии само-лечится через `EnsureCoreEmployeeLinked`.

## Корневая причина (гипотеза)
Асимметрия: для РД добавили авто-линковку Core-employee, для support забыли.

## Радиус поражения
Назначение саппортов на проекты для любого нелинкованного support-пользователя.

## Направление фикса (1-2 строки, НЕ реализовано)
Вызвать `EnsureCoreEmployeeLinked::execute($user)` в `addSupport()` перед созданием membership, по образцу РД.
