---
id: F-0086
flow: sklad-projects-admin
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaisklad_back, rusaicore]
status: open
---

## Симптом
`DELETE /admin/users/{id}` в sklad удаляет local `User` + local memberships + assignments в транзакции, но Core employee и Core memberships остаются (reverse-orphan). При следующем `core:shadow-sync` удалённый юзер ре-материализуется локально («воскрешение»).

## Доказательства (file:line)
- `rusaisklad_back/app/Http/Controllers/API/Users/UserController.php:720-731` — `destroy()` → `managementService->delete()`.
- `rusaisklad_back/app/Services/User/UserManagementService.php:71-82` — `DB::transaction`: удаляет local `Assignment`, `$user->memberships()->delete()` (local pivot), `$user->delete()`. Ни одного Core-вызова.
- `rusaisklad_back/app/Domain/Core/Sync/CoreEmployeeShadowSyncService.php` — `createLocalAnchor` односторонне ре-создаёт local anchor для каждого Core employee при следующем синке.

## Триггер / repro
Удалить через sklad-admin юзера с заполненным `external_user_id` (есть Core employee). В Core остаётся employee+memberships → reverse-drift; следующий `core:shadow-sync` снова создаёт local anchor → удалённый юзер «воскресает».

## Корневая причина (гипотеза)
Удаление не каскадит в Core, а shadow-sync однонаправленно (Core→sklad) ре-материализует. Тот же незакрытый user-write-путь, что F-0085 (reverse-сторона). Класс F-0002.

## Радиус поражения
Удаление любого Core-связанного юзера через sklad: Core-orphan + повторное появление юзера после синка (рассинхрон состояния, путаница оператора).

## Направление фикса
Запретить локальное удаление Core-связанных юзеров (guard) либо проводить удаление через Core с последующим синком. См. F-0085.
