# Russ360 / Russmarket 360 — проектный контекст

## Что это
Платформа Russmarket 360 — экосистема из 4 Laravel-сервисов и 2 Nuxt-фронтов. **OAuth2/OIDC активен в проде** (rusaiauth — IdP). M2-cutover завершён 2026-05-13. Stage 1 (rusaisklad core domain: projects+memberships+locations) закрыт 2026-05-18. Текущая фаза: **post-cutover stabilization** + подготовка Stage 2 (переключение читателей rusaifin на Core contracts).

## Сервисы (бэкенд)

| Сервис | Директория | Порт | Роль |
|--------|-----------|------|------|
| **rusaicore** | `rusaicore/` | 8001 | Core: Employee, Project, OperationalLocation, ProjectMembership. Чистая слоистая архитектура (Domain/Application/Infrastructure/Http). OAuth resource server. |
| **rusaiauth** | `rusaiauth/` | 8002 | Identity/Access — OAuth2/OIDC provider (Laravel 12 + Passport, RS256 JWT). DB порт 5434. |
| **rusaifin** | `rusaifin/` | 8000 | Field Sales Operations — legacy monolith. OAuth resource server. |
| **rusaisklad_back** | `rusaisklad_back/` | 8003 | Inventory Operations. Имеет `Domain/Core/` адаптерный слой к rusaicore. OAuth resource server. |

## Локальная инфра — как поднимать

```bash
docker compose -f rusaiauth/compose.yml up -d
docker compose -f rusaicore/compose.yml up -d
docker compose -f rusaifin/compose.local.yml up -d
docker compose -p rusaisklad_back_local -f rusaisklad_back/compose.back.local.yaml up -d
```

**Важно:** для rusaisklad обязательно `-p rusaisklad_back_local`, иначе compose плодит дублирующие контейнеры по имени директории.

## Прод-инфра

- Сервер `82.146.57.149`, Hestia, host MySQL, docker per-service.
- SSO: `sso.rusaifin.ru` (rusaiauth), HTTPS обязателен.
- SSH через `sshpass` (см. allowlist). **Любые операции с прод — спрашивать.**

## Критичные quirks

### Laravel Passport не выставляет `iss` в JWT
Без патча resource server'ы возвращают 401 на ВСЕ токены.

- Файл: `rusaiauth/app/Domain/Identity/OAuth/IssuerAwareAccessToken.php` (extends `Laravel\Passport\Bridge\AccessToken`, переопределяет `toString()` через Reflection).
- Подключение: `Passport::useAccessTokenEntity(IssuerAwareAccessToken::class)` в `AppServiceProvider::configurePassport()`.
- Issuer: `config('oidc.issuer_url')`.
- При любом деплое rusaiauth — проверять, что `iss` присутствует в payload свежего токена.

### client_credentials → `sub === aud`
В `client_credentials` grant Passport ставит `sub = client_id`. Validator (rusaicore `OAuthTokenValidator`) нормализует: если `sub === aud` — считать client_credentials и обнулять sub.

### Минт smoke-токена
```bash
docker exec rusaiauth-app php /var/www/html/scripts/mint-smoke-token.php <user_uuid> <client_name> <scopes>
```
Минтит через `IssuerAwareAccessToken` без записи в DB (Passport `createToken` упирается в bigint user_id, а `identity_users.id` — UUID).

### Drop-миграции в `database/migrations/cutover/`
НЕ запускаются стандартным `php artisan migrate`. Только в окне cutover через `--path=database/migrations/cutover`.

## Принципы изменений

- **Big-bang cutover без feature flags** — пользователь так попросил. Не предлагать поэтапные миграции с feature flags.
- **rusaifin/rusaisklad guard возвращает полный User Eloquent**, не `OAuthPrincipal` (~200 контроллеров читают `auth()->user()->role_id`). rusaicore — наоборот, возвращает `OAuthPrincipal`, контроллеры читают `$principal->sub` / `->scopes`.
- `online_in` обновляется через `forceFill(['online_in' => now()])->saveQuietly()` в guard'е — без триггеров observers.

## Документация v2 (canonical)

`rusaicore/docs/russmarket360/`:
- `00-overview.md` — карта сервисов
- `01-identity-access-rusaiauth.md` — OAuth2/OIDC спека
- `02-core-extend.md` — расширение Core-домена
- `04-cutover-playbook.md` — Phase 1/2/3 cutover (ИСТОРИЧЕСКИЙ snapshot M2)
- `07-implementation-roadmap.md` — M0–M5 milestones (M0–M2.1 done; M3+ открыт)
- `08-production-deployment-checklist.md` — prod checklist (ИСТОРИЧЕСКИЙ snapshot 2026-05-12)
- `m2-completion-report.md` — отчёт о завершении M2
- `frontend-handoff.md` — спека для фронта (OIDC discovery, client_id'ы, PKCE, scopes)

Аудит расхождений архитектуры от факта: `docs/russ360-audit-2026-05-18.md` (корень монорепы).

## Тесты

- Trait `Tests\Feature\Concerns\AuthenticatesAsOAuthUser` (rusaifin/rusaisklad) для feature-тестов с OAuth.
- rusaicore: `WithDefaultOAuthUser` trait + `AuthenticatesOAuth`.
- Pre-existing Sanctum-тесты `tests/Feature/AuthTest` в rusaisklad скипнуты — переписать через trait при необходимости.

## Обучение системе и состояние автора

Автор изучает систему и стабилизирует прод после M2/Stage1 cutover. Перед началом любой работы агент должен прочитать:

1. **`docs/russ360-audit-2026-05-18.md`** — свежий аудит реального состояния системы (P0/P1/P2 находки, фактический matrix «сущность × сервис»).
2. **`docs/russ360-deep-dive.md`** — техническая карта системы (OAuth flow, PKCE, JWT, прод-инфра, грабли). Дата сборки 2026-05-04 — пред-cutover snapshot; для текущего состояния сверяться с аудитом.
3. **`docs/learning-progress.md`** — где автор сейчас в обучении, какие темы прошёл, какие открытые вопросы. Обновляй после значимых сессий.
4. **`docs/russ360-learning-curriculum.md`** — двухчасовый сквозной материал по системе. Содержит честную архитектурную оценку — не противоречь ей без причины.

### Правила взаимодействия с автором

- Автор **единственный backend разработчик**, склонен к параличу действий из-за информационной перегрузки. Не предлагай большие рефакторинги или новые архитектурные решения без явного запроса.
- Когда автор просит «объяснить» — открывай **реальные файлы кода** и комментируй построчно. Не давай абстрактных лекций.
- Когда автор просит «сделать» — сначала уточни, что именно сделать, потом покажи план в ~3 пунктах, и только после «иди» — действуй.
- На любые операции с прод-сервером (`82.146.57.149`) — обязательно явное «иди на прод». Read-only ssh-разведка ок без подтверждения.

### Архитектурная позиция (не пересматривай по своей инициативе)

- 4 backend-сервиса (rusaiauth, rusaicore, rusaifin, rusaisklad_back). Возможно, разрезано избыточно (rusaicore + один из доменных сервисов могли бы быть одним сервисом). Это известно, обсуждено в Прогоне 5 курикулума.
- Решение: M2 cutover закрыт; **сейчас фокус — пост-cutover стабилизация и Stage 2** (переключение читателей `rusaifin` на Core-контракты). Слияния сервисов не обсуждаются до завершения Stage 2.
- rusaiauth как отдельный сервис **выделен правильно** (security boundary). Это не обсуждается.

### Технические инварианты, которые легко нарушить случайно

- **Никогда** не запускай `php artisan migrate` в rusaiauth/rusaicore без проверки, что в `database/migrations/cutover/` не лежат миграции, которые применяться сейчас не должны. Cutover-миграции запускаются только с `--path=database/migrations/cutover` и только в окно cutover.
- При деплое rusaiauth — **обязательно** проверять, что `iss` присутствует в payload свежевыпущенного JWT (см. quirk 5.1). Без `iss` все resource server'ы вернут 401 на все токены.
- В rusaisklad-локали запускать compose **только** с `-p rusaisklad_back_local`, иначе плодятся дубли.
- Контракт guard'а различается между сервисами (см. quirk 5.6): rusaifin/rusaisklad возвращают полный `User` Eloquent, rusaicore — `OAuthPrincipal`. Не пытаться унифицировать без обсуждения.

### Где лежат ключевые файлы (для быстрой навигации)

- Frontend OIDC-клиент: `src/shared/lib/oidcPkce.ts`, `src/shared/lib/oidcRefresh.ts` в обоих фронтах
- Custom JWT issuer fix (rusaiauth): `app/Domain/Identity/OAuth/IssuerAwareAccessToken.php`
- Token validator (rusaicore): см. `OAuthTokenValidator` (нормализация `sub === aud`)
- Документация v2: `rusaicore/docs/russmarket360/`
- Smoke-token mint (без БД): `rusaiauth/scripts/mint-smoke-token.php`

