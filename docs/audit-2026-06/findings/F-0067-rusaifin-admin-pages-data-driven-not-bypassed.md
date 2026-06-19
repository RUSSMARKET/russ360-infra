---
id: F-0067
flow: role-pages-permissions
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

Permission-резолв и page-резолв используют РАЗНЫЕ модели admin-bypass: права (`hasPermission`/`hasAccess`) захардкоживают `true` для ADMIN (role_id=1), а страницы (`getPages`) читаются чисто из `role_pages` даже для админа. Если `role_pages` для role_id=1 пуст (см. F-0065), у админа меню навигации пустое, но при этом полный доступ к API — рассинхрон UX/authz.

## Доказательства (file:line)

- `rusaifin/app/Services/User/UserService.php:139-142` — `getPages()`: всегда `Role::find($role_id)->pages()`, ветки admin-bypass нет.
- `rusaifin/app/Services/User/UserService.php:638` — `hasPermission`: `if ($this->user->role_id === RoleEnum::ADMIN->value) return true;` (захардкоженный bypass).
- `rusaifin/app/Http/Controllers/System/RoleController.php` (`hasAccess`) — аналогичный admin-bypass `true` без чтения pivota; в `getPages`-ветке RoleController для admin лишь добавляет `hidden`, базовые pages всё равно из `role_pages`.

## Триггер / repro

`role_pages` для role_id=1 пуст (свежая БД / DR без переноса) → админ (юзер 40 Альбина) видит меню пустым, но все API-эндпоинты доступны. На текущем проде замаскировано наличием ручных данных в `role_pages`.

## Корневая причина (гипотеза)

Несогласованность двух моделей bypass: permissions — захардкоженный admin-bypass, pages — чисто data-driven из `role_pages`. Класс F-0065 (незасиженный baseline) усиливает эффект для админа.

## Радиус поражения

Админ-аккаунт при потере `role_pages`. Латентно, замаскировано прод-данными. Минор.

## Направление фикса

Либо добавить admin-bypass в `getPages` (возвращать `Pages::all()` для ADMIN), либо явно зафиксировать, что админ-меню data-driven, и гарантировать baseline-seed (F-0065).
