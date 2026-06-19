---
id: F-0056
flow: staff-management
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Блокировка/разблокировка сотрудника в rusaifin не синхронизирует статус Core Employee. `CoreEmployeeWriteGateway::update(status:)` существует, но в потоке staff-management не вызывается. Core directory показывает заблокированных как `active`.

## Доказательства (file:line)
- `app/Http/Controllers/Staff/StaffController.php:1103` — `blockStaff` → `$staff->disable(true)`.
- `app/Services/User/UserService.php:194-212` — `disable()` делает только `clearTraineeshipOnBlock` + `detachFromProjectsAndPoints()` + `$this->user->disabled = …; save()`. Core Employee status не трогается.
- `app/Domain/Core/Gateways/CoreEmployeeWriteGateway.php:38-59` — метод `update(status:)` есть, но в staff-flow используется только `EnsureCoreEmployeeLinked::execute()` (зовёт лишь `create`); вызовов `update(status:)` нет.

## Триггер / repro
Заблокировать сотрудника через `POST /api/staff/{id}/off`. В Core `employees.status` остаётся `active`.

## Корневая причина (гипотеза)
Block покрывает rusaifin-локальный `disabled` + завершение Core memberships/assignments, но сам Employee-агрегат в Core никогда не переводится в неактивный статус. Write-side counterpart к reader-side F-0026/F-0027.

## Радиус поражения
Core Employee directory и его потребители (rusaisklad, отчёты) видят заблокированного как active. Для агентов смягчено завершением assignments (`detachFromProjectsAndPoints`); для остальных ролей — рассинхрон статуса. Не цельная блокировка доступа, а рассогласование directory-статуса.

## Направление фикса (1-2 строки, НЕ реализовано)
В `disable(true/false)` при наличии `core_employee_external_id` вызывать `CoreEmployeeWriteGateway::update(status: 'inactive'|'active')`.
