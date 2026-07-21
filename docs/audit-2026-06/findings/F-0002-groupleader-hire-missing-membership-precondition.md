---
id: F-0002
flow: hiring-onboarding
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin, rusaicore]
status: closed
---
## Симптом
Оформление сотрудника на роль «Групп-лидер» (GROUP_LEADER) с указанием точек падает с `InvalidArgumentException('Агент должен быть привязан к проекту точки…')`. Сотрудник не оформляется на точку, при этом `role_id` уже сменён и сохранён, Core-employee уже создан — частично применённое состояние.

## Доказательства (file:line)
- `rusaifin/app/Services/Project/PointService.php:194-218` — `setGroupLeader()` сразу вызывает `coreCreateAssignment($empExt,$locExt,ROLE_LEADER)` (строка 216) БЕЗ предварительного `ensureActiveProjectMembershipForAssignment()`.
- Контраст: `PointService.php:226-243` — `addAgent()` на строке 235 ВЫЗЫВАЕТ `ensureActiveProjectMembershipForAssignment($employeeExternalId)` перед `coreCreateAssignment`.
- `PointService.php:280-287` — на membership-required conflict Core ошибка ре-бросается как `\InvalidArgumentException('Агент должен быть привязан к проекту точки. Не удалось создать membership в Core.')`.
- `rusaicore/app/Application/OperationalLocationAssignment/Actions/CreateOperationalLocationAssignment.php:54-99` — `assertActiveMembershipExists()` требует активного membership для ЛЮБОЙ открытой ассигнации (любой роли), иначе `membershipRequiredForLocationAssignment`.

## Триггер / repro
`POST staff/registration/{id}/role` с `role_id=GROUP_LEADER` и непустым `points_id` для свежего hire (нет активного ProjectMembership в Core) → Core 409 membership_required → исключение, оформление прерывается.

## Корневая причина (гипотеза)
Асимметрия write-путей: `addAgent` создаёт project membership перед location-assignment, `setGroupLeader` — нет, хотя Core требует membership для location-assignment любой роли. Unit-тест `tests/Unit/Project/PointServiceWriterTest.php:87-112` использует фейковый Core, безусловно отдающий 201 и не сидящий membership → зелёный тест маскирует дефект.

## Радиус поражения
Все оформления/переназначения групп-лидера на точку через `setRegistrationRole`, плюс любой иной вызов `PointService::setGroupLeader` (смена РГ точки). Агентский путь не затронут.

## Направление фикса (1-2 строки, НЕ реализовано)
В `setGroupLeader` вызвать `ensureActiveProjectMembershipForAssignment($empExt)` перед `coreCreateAssignment` (по аналогии с `addAgent`); добавить тест с реальным membership-precondition.

## Статус закрытия

Проверено по коду на `origin/main` 2026-07-21 — дефект устранён.
`PointService::setGroupLeader` вызывает `ensureActiveProjectMembershipForAssignment(..., GROUP_LEADER)` ДО `coreCreateAssignment` (после `EnsureCoreEmployeeLinked`); сам метод создаёт membership при отсутствии.
