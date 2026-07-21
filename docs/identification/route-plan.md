# План обхода интерфейсов — идентифицирующие материалы russ360

Источник: **dev-контур** (визуально идентичен проду, тестовые данные, без PII).
Охват: 3 поверхности, ключевые экраны. Скриншоты снимает Playwright MCP.

## Базовые URL (dev)

| Поверхность | Base URL | client_id (dev) | scopes |
|---|---|---|---|
| auth-SPA (IdP) | https://dev.sso.rusaifin.ru/auth | — | openid profile email phone |
| fintech (rusaifin) | https://dev.fintech.rusaifin.ru | `019df247-8dd3-73bf-8f0d-58b742672c22` | `fieldsales.read fieldsales.write` |
| sklad (rusaisklad) | https://dev.rusaisklad.ru | (см. nuxt.config) | `inventory.read inventory.write` |

## Роли для обхода (тест-персоны dev)

- **ADMIN** (role_id=1, fintech) — полный bypass, видит всё (kpi/admin/reporting).
- **СВ / супервайзер** — проектные membership-страницы.
- **Консультант** — базовый доступ (home/products/profile).
- Конкретные логины/телефоны — из memory `test_personas` (OTP-обход debug_code на dev).

## auth-SPA — экраны (без логина, проходятся по шагам формы)

| # | Экран | Код |
|---|---|---|
| 1 | LoginPhone (ввод телефона) | `rusaiauth/resources/js/preview/pages/LoginPhonePage.vue` |
| 2 | LoginCode (ввод кода/пароля) | `LoginCodePage.vue` |
| 3 | LoginSystemSelect (выбор системы fin/sklad) | `LoginSystemSelectPage.vue` |
| 4 | RegisterPhone | `RegisterPhonePage.vue` |
| 5 | (опц.) RecoveryPhone | `RecoveryPhonePage.vue` |

## fintech — ключевые экраны

| # | Route | Страница (.vue) | Роль | Ключ. |
|---|---|---|---|---|
| 1 | `/auth` | `pages/auth/ui/Auth.vue` | — | ★ |
| 2 | `/registration` | `pages/registration/ui/Registration.vue` | — | ★ |
| 3 | `/` (home) | `pages/home/ui/Home.vue` | любая | ★ |
| 4 | `/products` | `pages/products/ui/Products.vue` | любая | ★ |
| 5 | `/kpi` | `pages/kpi/ui/Kpi.vue` | СВ/admin | ★ |
| 6 | `/reporting` | `pages/reporting/ui/Reporting.vue` | СВ/admin | ★ |
| 7 | `/requests` | `pages/requests/ui/Requests.vue` | любая | ★ |
| 8 | `/profile` | `pages/profile/ui/Profile.vue` | любая | ★ |
| 9 | `/admin` | `pages/admin/ui/Admin.vue` | admin | ★ |
| 10 | `/agents` | `pages/agents/ui/Agents.vue` | СВ/admin | |
| 11 | `/tasks` | `pages/tasks/ui/Tasks.vue` | любая | |
| 12 | `/inventory` | `pages/inventory/ui/Inventory.vue` | любая | |

## sklad — ключевые экраны

| # | Route | Страница (.vue) | Роль | Ключ. |
|---|---|---|---|---|
| 1 | `/auth` | `pages/auth/ui/Auth.vue` | — | ★ |
| 2 | `/` (home) | `pages/home/ui/Home.vue` | любая | ★ |
| 3 | `/products` | `pages/products/ui/Products.vue` | любая | ★ |
| 4 | `/sku` | `pages/sku/ui/Sku.vue` | любая | ★ |
| 5 | `/inventory` (ТМЦ) | `pages/inventory_tmc/ui/InventoryTmcShell.vue` | любая | ★ |
| 6 | `/users` | `pages/users/ui/Agents.vue` | admin/СВ | ★ |
| 7 | `/admin` | `pages/admin/ui/Admin.vue` | admin | ★ |
| 8 | `/registration` | `pages/registration/ui/Registration.vue` | — | |
| 9 | `/project` | `pages/project/ui/Project.vue` | любая | |

## Подводные камни обхода

- **409 PROJECT_SELECTION_REQUIRED** — перед проектными страницами выбрать проект (sklad: `/project-selection`).
- **Роль-гейтинг** — kpi/admin/reporting/users снимать под ADMIN/СВ, иначе редирект.
- **iOS-фон замораживает refresh** — не актуально для desktop-обхода.
- Скриншоты класть в `docs/identification/screens/<surface>-<route>.png` (имена ниже в генераторе).
