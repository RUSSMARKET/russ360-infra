---
id: F-0059
flow: staff-management
dimension: data-integrity
severity: P2
confidence: likely
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Смена роли сотрудника через `updateStaff` открепляет от Core (memberships/assignments → ended), но НЕ создаёт Core-привязки для новой роли и не обновляет Core Employee. Сотрудник остаётся с новой ролью в rusaifin без соответствующих Core-memberships → «невидимый»/нерабочий в потребителях Core (тот же класс, что visibility-orphans backfill 2026-05-28, но на пути смены роли).

## Доказательства (file:line)
- `app/Http/Controllers/Staff/StaffController.php:581-588` — при изменении `role_id`: `(new UserService($user))->detachFromProjectsAndPoints(); $user->update($validated);`. Последующего attach под новую роль нет.
- `app/Services/User/UserService.php:812-844` — `detachFromProjectsAndPoints` только завершает существующие Core-привязки по СТАРОЙ роли.

## Триггер / repro
Сменить роль агента → group_leader через `PUT /api/staff/{id}`. Старые agent-assignments завершены, новых GL-привязок в Core нет; rusaifin `role_id=GL` → сотрудник без Core-membership до ручной привязки.

## Корневая причина (гипотеза)
`updateStaff` делает только локальный `update($validated)` + одностороннее detach; re-provisioning под новую роль — ответственность отдельных endpoint'ов привязки, в update не вызывается.

## Радиус поражения
Сотрудник со сменённой ролью без Core-memberships до ручной привязки; рассинхрон роли rusaifin↔Core, пустая видимость (родственно F-0052 и known visibility-orphans).

## Направление фикса (1-2 строки, НЕ реализовано)
После смены роли инициировать re-provisioning Core-membership под новую роль, либо явно сделать 2-шаговый flow (смена роли → обязательная привязка) с защитой от «висящего» состояния.
