---
id: F-0065
flow: role-pages-permissions
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

Таблицы `pages` и `role_pages` ничем не наполняются в коде (нет сидера, нет data-insert в миграции). На чистой БД ВСЕ роли получают пустой набор страниц → фронт показывает «нет доступных страниц» для всех, включая валидные роли. Прод работает только потому, что эти таблицы наполнены вручную и существуют как незафиксированное состояние.

## Доказательства (file:line)

- `rusaifin/database/migrations/2025_07_29_074257_create_pages.php:14-25` — создаёт `pages` и `role_pages`, НИ ОДНОГО `insert`/`DB::table()->insert` (grep по миграции пуст).
- `rusaifin/database/seeders/DatabaseSeeder.php:15-18` — `call([...])` содержит только `SeedMagnitProjectPointsAndAgentsSeeder`, `SeedMagnitProjectAgentsSeeder`. Сидеров `pages`/`role_pages` нет (`grep -rln "role_pages|Page::insert|Page::create"` по `database/` → только сама миграция).
- `rusaifin/app/Services/User/UserService.php:139-142` — `getPages()`: `$role = Role::find($this->user->role_id); return $role->pages()...` — читает `role_pages` напрямую, без baseline.
- `role_pages` имеет composite PK `primary(['role_id','page_id'])` (миграция `:24`) → дубли невозможны (это чисто); проблема — пустота, не дубли.

## Триггер / repro

Поднять чистую rusaifin БД, прогнать `migrate --seed` → залогиниться любой ролью → `getPages()` возвращает пустую коллекцию → `pages.value` пуст в bibli AppNavigation. Сценарии: CI feature-тесты authz, новый dev-инстанс, DR-restore без переноса `pages`/`role_pages`.

## Корневая причина (гипотеза)

`pages`/`role_pages` ведутся исключительно вручную через админ-эндпоинты (`/api/pages`, `/api/role/page/add`). Нет идемпотентного baseline-сидера. На проде данные наполнены руками; refresh-dev-from-prod подтягивает их из дампа, но чистый seed их теряет → прод-состояние навигации невоспроизводимо.

## Радиус поражения

Любой fresh-env: CI authz-тесты, новый dev, DR-restore без переноса этих таблиц → тотальная потеря навигации. На текущем проде НЕ проявляется (данные есть) — отсюда P2, а не P1.

## Направление фикса

Добавить идемпотентный `PagesAndRolePagesSeeder` (baseline pages + дефолтный role_pages-маппинг по ролям), включить в `DatabaseSeeder::call`.
