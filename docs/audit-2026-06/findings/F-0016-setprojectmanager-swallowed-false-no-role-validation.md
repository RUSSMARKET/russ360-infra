---
id: F-0016
flow: project-support-membership
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
`createProject`/`updateProject` не валидируют роль кандидата в PM и игнорируют результат `setProjectManager`: при не-PM пользователе PM молча НЕ назначается, но API возвращает 200.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Project/ProjectController.php:278-280` (`createProject`) и `:410-412` (`updateProject`) — `$projectService->setProjectManager((int)$projectManagerId)` без проверки результата.
- `ProjectService.php:116-118` — `setProjectManager()`: `if ($user->role_id != PROJECT_MANAGER) return false;` молча.
- Валидация в контроллере — только `exists:users,id`, роль не проверяется (для РД роль валидируется через `assertRegionalDirectorUser`).

## Триггер / repro
Передать `project_manager_id` пользователя с ролью ≠ PROJECT_MANAGER → 200, но PM не назначен ни в Core, ни (legacy заморожен) нигде. Оператор считает, что назначил.

## Корневая причина (гипотеза)
Проглоченный boolean-результат + отсутствие role-валидации PM.

## Радиус поражения
Тихое неназначение PM при create/update проекта.

## Направление фикса (1-2 строки, НЕ реализовано)
Валидировать роль PM в контроллере (как для РД) и/или бросать ошибку при `false` от `setProjectManager`.
