---
id: F-0060
flow: staff-management
dimension: data-integrity
severity: P2
confidence: likely
services: [rusaifin, rusaicore]
status: open
---
## Симптом
`createStaff` без транзакции и с условным созданием Core-сущностей: (1) для ролей без активного проекта (support_manager/regional_director/project_manager при пустом `projectService`) Core-membership молча пропускается и Core Employee не создаётся → свежий orphan; (2) при многоточечном найме агента падение `addAgent` на N-й точке оставляет частичную запись (rusaifin user создан + часть Core-write выполнена) без компенсации.

## Доказательства (file:line)
- `app/Http/Controllers/Staff/StaffController.php:393` — `User::Create($validated)` без транзакции.
- `app/Http/Controllers/Staff/StaffController.php:406-421, 460-466` — `if ($projectService) { $projectService->addSupport(...) }` и аналогично RD/PM: при отсутствии проекта шаг пропускается → Employee в Core не появляется.
- `app/Http/Requests/Staff/CreateStaffRequest.php:190-197` — `addAgentPoints` циклом зовёт `addAgent` (Core HTTP) без обёртки транзакции/компенсации.

## Триггер / repro
1) Админ создаёт support_manager без активного проекта → rusaifin user есть, Core Employee нет (orphan; родственно F-0002, но на прямом create-пути, не registration). 2) Создать агента на 2 точки, вторая `addAgent` падает → частичная привязка без отката.

## Корневая причина (гипотеза)
Создание Core-сущностей завязано на наличие `projectService`/успех всех точек; нет гарантированного `EnsureCoreEmployeeLinked` на входе для всех ролей и нет транзакции/компенсации на create-пути.

## Радиус поражения
Orphan-сотрудники с непроектными ролями (тот же класс, что known orphan-регрессия, но другой entry point); частичные привязки при сбое точки.

## Направление фикса (1-2 строки, НЕ реализовано)
Гарантировать `EnsureCoreEmployeeLinked::execute()` для всех ролей до привязок; обернуть create+привязки в транзакцию/saga с компенсацией Core-write.
