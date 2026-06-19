---
id: F-0066
flow: role-pages-permissions
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

Если `users.role_id` указывает на несуществующую роль (orphan/рассинхрон), authz-резолв ломается по-разному в разных местах: `getPages()` падает 500 (`->pages()` on null), а `/api/user/permissions` тихо возвращает пустой 200 без `status` — фронт не отличает «нет прав» от ошибки.

## Доказательства (file:line)

- `rusaifin/app/Services/User/UserService.php:141-142` — `$role = Role::find($this->user->role_id); return $role->pages()...` без проверки `$role` на null → `Call to a member function pages() on null` (500). Вызывается на логине (через `AuthController` authPayload) и на `/api/pages`.
- `rusaifin/app/Http/Controllers/User/UserController.php` (`getUserPermissions`) — `if ($role) { return ...; }` без `else` → при `$role===null` возвращает `null` → пустой 200.

## Триггер / repro

Юзер с `role_id`, которого нет в `roles` (роль рассинхронена/мягкий FK) → 500 на логине / пустой 200 на `/api/user/permissions`. Вероятность низкая: `RoleController::deleteRole` имеет закомментированный реальный `$role->delete()` — роли фактически не удаляются, поэтому orphan-role редок (отсюда P3, latent).

## Корневая причина (гипотеза)

Отсутствие null-guard после `Role::find($role_id)` в нескольких точках authz-резолва; разная обработка одного и того же orphan-role класса (500 vs тихий 200).

## Радиус поражения

Узкий (требует битого `role_id`). Happy-path логина → 500 вместо graceful empty; permissions-эндпоинт → неоднозначный ответ.

## Направление фикса

Добавить null-guard: `$role = Role::find(...); if (!$role) return collect();` в `getPages`; в `getUserPermissions` добавить `else` с явным `status:false`/404.
