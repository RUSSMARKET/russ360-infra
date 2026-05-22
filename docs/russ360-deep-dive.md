# Russ360 / Russmarket 360 — обучающий конспект

> Цель: дать одному человеку (или новому агенту) полную ментальную модель платформы и фазы M2 OAuth-cutover'а, чтобы он мог самостоятельно ориентироваться в коде, инфре, токенах, граблях и оставшихся задачах.
>
> Дата сборки: **2026-05-04** (snapshot перед prod-cutover). Источники: CLAUDE.md (root + проектный), MEMORY-индекс, прод-сервер `82.146.57.149` (read-only ssh-снимок фронтов).
>
> ⚠️ **Этот документ — snapshot до prod-cutover.** Prod-cutover пройден 2026-05-13. Для текущего фактического состояния сверяться с `russ360-audit-2026-05-18.md` (расхождения архитектуры от факта, P0/P1/P2 находки).

---

## 1. Что такое Russmarket 360

Платформа из **4 Laravel-сервисов** и **2 Nuxt-фронтов**. На момент сборки конспекта (2026-05-04) — финальная фаза M2: миграция авторизации с legacy `api_token` (Sanctum-style) на **OAuth2 / OIDC Bearer JWT**, где `rusaiauth` — Identity Provider. **Prod-cutover закрыт 2026-05-13** — OAuth активен везде. Legacy `api_token` выпилен.

### 1.1 Backend-сервисы

| Сервис | Директория | Порт | Роль | Архитектура |
|---|---|---|---|---|
| **rusaicore** | `rusaicore/` | 8001 | Core-домен: Employee, Project, OperationalLocation, ProjectMembership | Чистая слоистая (Domain / Application / Infrastructure / Http). OAuth resource server. |
| **rusaiauth** | `rusaiauth/` | 8002 | Identity & Access — OAuth2/OIDC provider | Laravel 12 + Passport, RS256 JWT. Postgres на 5434. |
| **rusaifin** | `rusaifin/` | 8000 | Field Sales Operations | Legacy-монолит. OAuth resource server. |
| **rusaisklad_back** | `rusaisklad_back/` | 8003 | Inventory Operations | `Domain/Core/` адаптерный слой к rusaicore. OAuth resource server. |

### 1.2 Frontend-сервисы

| Фронт | Стек | Прод-домен | Dev-домен | Расположение на проде |
|---|---|---|---|---|
| **rusaifin-front** (директория `fintech`) | Nuxt 3 + Vue 3 + Pinia + axios | `fintech.rusaifin.ru` | `dev.fintech.rusaifin.ru` | `/home/fintech/web/<domain>/public_html` |
| **rusaisklad-front** | Nuxt 3 + Vue 3 + Pinia + axios | `rusaisklad.ru` | `dev.rusaisklad.ru` | `/home/Rusaisklad/web/<domain>/app` |

UI-библиотека общая — `bibli` (`github:RUSSMARKET/russ-ui#main`), монорепная философия с переключением на локальную копию через `NUXT_LOCAL_BIBLI_PATH`.

OIDC-библиотек **нет**: PKCE-клиент написан вручную в `src/shared/lib/oidcPkce.ts` + `src/shared/lib/oidcRefresh.ts` — на WebCrypto API без зависимостей.

WebSocket — `rusaifin-ws` (Laravel Reverb), отдельные контейнеры `rusaifin_ws_prod-reverb-1` и `rusaifin_ws_stage-reverb-1`.

### 1.3 Карта сервисов на проде (docker ps, 2026-05-04)

```
rusaiauth_back_dev-app, rusaiauth_back_dev-db (postgres:16-alpine)
rusaicore_back_{dev,prod}-{app,nginx,pgsql}
rusaifin_ws_{prod,stage}-reverb-1
rusaisklad_back_{dev,prod}-{app,nginx,pgsql,redis}
rusaisklad_front_{dev,prod}-nuxt-dev-1
```

`rusaifin_back` контейнера в docker нет — rusaifin крутится напрямую через php-fpm под Hestia (legacy-монолит).

---

## 2. Локальная инфра

```bash
docker compose -f rusaiauth/compose.yml up -d
docker compose -f rusaicore/compose.yml up -d
docker compose -f rusaifin/compose.local.yml up -d
docker compose -p rusaisklad_back_local -f rusaisklad_back/compose.back.local.yaml up -d
```

⚠️ Для rusaisklad — обязательно `-p rusaisklad_back_local`, иначе compose плодит дубли по имени директории.

Локальная БД: host MySQL `127.0.0.1:3306`. У rusaiauth — отдельный Postgres на 5434.

---

## 3. Прод-инфра

| Параметр | Значение |
|---|---|
| Хост | `82.146.57.149` (`a.shake.fvds.ru`, Ubuntu, Linux 5.15) |
| Панель | Hestia |
| БД | host MySQL + per-service Postgres |
| Контейнеризация | docker per-service |
| SSO | `sso.rusaifin.ru` (prod), `dev.sso.rusaifin.ru` (dev) |
| HTTPS | Обязательно для всех публичных доменов |
| SSH | Key-based; `sshpass` тоже разрешён, но ключа достаточно |
| Известные gotchas | timeweb AAAA-leak (см. memory `prod_infrastructure.md`) |

**Любые операции с прод — спрашивать.** Read-only ssh-разведка ок, всё остальное — после явного «иди».

---

## 4. Identity & Access — теоретический минимум

### 4.1 Зачем OAuth2/OIDC, а не api_token

`api_token` (Sanctum-style) — статичная строка, без TTL, без scope'ов, без issuer-проверки. Любой ресурс-сервер тупо сравнивает строку с БД. Минусы:

- Нет M2M клиентов с ограниченными правами (нельзя выдать токен «только на чтение каталога»).
- Нет ротации, нет короткоживущих токенов.
- Любая утечка строки = полный доступ навсегда, пока не отозвана вручную.
- Нет стандарта — каждый сервис изобретает свою схему refresh / revoke.

**OAuth2** даёт grant'ы под разные сценарии:
- `authorization_code` + **PKCE** — для SPA / мобильных приложений (без client_secret на клиенте).
- `client_credentials` — для M2M (сервер-сервер) без user-context.
- `refresh_token` — продлить access_token без повторного логина.

**JWT** даёт self-contained токен: resource server проверяет подпись по JWKS публичному ключу — не нужно ходить в auth-сервис на каждый запрос.

**OIDC** поверх OAuth2 добавляет identity-слой: `id_token` (JWT с claim'ами о пользователе), `userinfo` endpoint, discovery (`/.well-known/openid-configuration`).

### 4.2 PKCE flow для SPA (используется в обоих фронтах Russ360)

```
┌─────────┐                                          ┌──────────────┐
│  Front  │                                          │  rusaiauth   │
│ (Nuxt)  │                                          │   (IdP)      │
└────┬────┘                                          └──────┬───────┘
     │ 1. generate code_verifier (43-128 chars)            │
     │    SHA256(code_verifier) -> code_challenge          │
     │    state = uuid()                                   │
     │    store {verifier, state} в sessionStorage         │
     │                                                     │
     │ 2. window.location.assign(                          │
     │      issuer/oauth/authorize                         │
     │        ?response_type=code                          │
     │        &client_id=...                               │
     │        &redirect_uri=.../auth/callback              │
     │        &scope=openid profile email phone ...        │
     │        &code_challenge=...                          │
     │        &code_challenge_method=S256                  │
     │        &state=...                                   │
     │    )                                                │
     ├────────────────────────────────────────────────────>│
     │                                                     │
     │ 3. user logs in (форма rusaiauth) → consent (auto?) │
     │                                                     │
     │ 4. 302 redirect_uri?code=...&state=...              │
     │<────────────────────────────────────────────────────┤
     │                                                     │
     │ 5. /auth/callback page mounted:                     │
     │    - читает {verifier, state} из sessionStorage     │
     │    - сверяет state                                  │
     │    - POST issuer/oauth/token                        │
     │      grant_type=authorization_code                  │
     │      code, redirect_uri, client_id, code_verifier   │
     ├────────────────────────────────────────────────────>│
     │                                                     │
     │ 6. {access_token (JWT), refresh_token, id_token,   │
     │     expires_in, token_type: Bearer}                │
     │<────────────────────────────────────────────────────┤
     │                                                     │
     │ 7. сохраняет:                                       │
     │    - localStorage.access_token                      │
     │    - localStorage.oidc_refresh_token                │
     │    - localStorage.oidc_access_expires_at_ms         │
     │    - очищает PKCE из sessionStorage                 │
     │                                                     │
     │ 8. GET /api/auth/me (Bearer JWT)                    │
     │    → { phone, name, role, pages, hidden, user{...} }│
     │                                                     │
     │ 9. scheduleProactiveOidcRefresh() —                 │
     │    setTimeout за 5 минут до exp                     │
```

### 4.3 client_credentials flow (M2M)

Сервер-сервер. Клиент шлёт `client_id` + `client_secret` → получает access_token без user-context. У такого токена `sub === aud === client_id` (см. quirk 5.2).

### 4.4 Структура JWT в Russ360

- Алгоритм: **RS256** (асимметричный, публичный ключ — JWKS endpoint rusaiauth).
- Обязательные claim'ы: `iss`, `sub`, `aud`, `exp`, `iat`, `scopes`.
- `iss` = `config('oidc.issuer_url')` — выставляется через кастомный access-token entity (см. quirk 5.1).

---

## 5. Критические quirks (без знания которых система не работает)

### 5.1 Laravel Passport не выставляет `iss` в JWT

Из коробки Passport кладёт минимальный набор claim'ов и **без `iss`**. Без патча resource server'ы (rusaicore, rusaifin, rusaisklad) возвращают **401 на ВСЕ токены**, потому что `OAuthTokenValidator` требует `iss`.

**Решение:**
- `rusaiauth/app/Domain/Identity/OAuth/IssuerAwareAccessToken.php` extends `Laravel\Passport\Bridge\AccessToken`, переопределяет `toString()` через Reflection (родительские свойства приватные).
- Регистрируется в `AppServiceProvider::configurePassport()` через `Passport::useAccessTokenEntity(IssuerAwareAccessToken::class)`.
- `iss` берётся из `config('oidc.issuer_url')`.
- ✅ После любого деплоя rusaiauth — проверять, что `iss` есть в payload свежего токена.

### 5.2 `client_credentials` → `sub === aud`

В `client_credentials` grant'е Passport кладёт `sub = client_id`, который равен `aud`. `OAuthTokenValidator` (rusaicore) **нормализует**: если `sub === aud` → считать токен M2M и обнулить `sub` (юзера в этом контексте нет, есть только client).

### 5.3 Минт smoke-токена (без UI, без БД)

```bash
docker exec rusaiauth-app php /var/www/html/scripts/mint-smoke-token.php <user_uuid> <client_name> <scopes>
```

Минтит токен через `IssuerAwareAccessToken` **без записи в БД**. Это нужно потому что Passport `createToken` упирается в `bigint user_id`, а в нашем `identity_users.id` — UUID. Стандартный путь через Passport ломается, поэтому минт идёт в обход.

### 5.4 Drop-миграции в `database/migrations/cutover/`

**Не запускаются** стандартным `php artisan migrate`. Только в окне cutover через `php artisan migrate --path=database/migrations/cutover`. Сделано чтобы случайно не уронить старые таблицы во время обычного деплоя.

### 5.5 Big-bang cutover без feature flags

По явной просьбе пользователя — не предлагать поэтапные миграции с feature flags. Один cutover-окно, один заход.

### 5.6 Контракт guard'а отличается между сервисами

| Сервис | Guard возвращает | Почему |
|---|---|---|
| **rusaifin / rusaisklad** | Полный `User` Eloquent | ~200 контроллеров читают `auth()->user()->role_id` — переписывать слишком дорого |
| **rusaicore** | `OAuthPrincipal` | Контроллеры читают `$principal->sub`, `->scopes` — чистая архитектура с самого начала |

`online_in` обновляется через `forceFill(['online_in' => now()])->saveQuietly()` в guard'е — без триггеров observer'ов.

### 5.7 10 ключевых граблей dev-cutover'а (зафиксированы 2026-05-04)

См. memory `m2_dev_cutover_done.md`. Краткий список:

1. `bigint → uuid` в `identity_users` (схемная миграция)
2. `TrustProxies` — нужен для HTTPS за прокси
3. CORS между фронтами и rusaiauth/rusai-сервисами
4. Минимальный Login UI на rusaiauth (Blade)
5. Кастомный Hestia template для роутинга
6. Runtime network connect между docker-сетями (`docker network connect`)
7. `php8.3-pgsql` расширение не было в базовом образе
8. `CORE_API_BASE_URL` обязательно с `/v1`
9. Auth view contract — `Passport::authorizationView()` биндинг
10. `id_token` gap — Passport не выдавал id_token из коробки

---

## 6. Frontend OIDC — детальная техника

### 6.1 Где код

Оба Nuxt-фронта реализуют PKCE одинаково (с косметическими отличиями). Файлы (одинаковые имена в обоих проектах):

```
src/shared/lib/oidcPkce.ts      — генерация verifier/challenge, redirect, обмен code → token
src/shared/lib/oidcRefresh.ts   — refresh, persist, proactive scheduler
src/pages/auth/api/index.ts     — fetchAuthMe / applyBootstrapFromAuthMe
src/pages/auth/model/index.ts   — isUserSessionPresent, loadPassportAfterAuth
src/pages/auth/ui/Auth.vue      — кнопка «Войти» → startOidcLogin()
src/app/routes/auth/callback.vue — handler /auth/callback (см. ниже)
middleware/auth.global.ts       — клиентский редирект если токен есть и идёшь на /auth
middleware/auth.ts              — gating приватных страниц по localStorage.access_token
```

### 6.2 PKCE-генерация (`oidcPkce.ts`)

- `code_verifier`: длина **64 символа** по умолчанию (RFC 7636: 43–128). Алфавит — unreserved chars `A-Za-z0-9-._~`. Случайность через `crypto.getRandomValues(new Uint8Array(1))[0] % 66`.
- `code_challenge`: `base64url(SHA256(code_verifier))` через `crypto.subtle.digest('SHA-256', ...)`.
- `state`: `crypto.randomUUID()`.
- Хранение PKCE: **`sessionStorage`** (умирает с вкладкой — корректно).
- Ключи: `pkce_verifier`, `pkce_state`.

### 6.3 Authorization request

```ts
const u = new URL(`${issuer}/oauth/authorize`)
u.searchParams.set('response_type', 'code')
u.searchParams.set('client_id', config.oidcClientId)
u.searchParams.set('redirect_uri', config.oidcRedirectUri)
u.searchParams.set('scope', config.oidcScopes)
u.searchParams.set('code_challenge', challenge)
u.searchParams.set('code_challenge_method', 'S256')
u.searchParams.set('state', state)
window.location.assign(u.toString())
```

### 6.4 Callback handler (`src/app/routes/auth/callback.vue`)

```
1. читает route.query.code и .state
2. читает {verifier, state} из sessionStorage
3. сверяет state (защита от CSRF)
4. POST issuer/oauth/token grant_type=authorization_code
   form: code, redirect_uri, client_id, code_verifier
5. на успехе:
   - localStorage.access_token = tokens.access_token
   - User.personal.token = tokens.access_token
   - persistOidcTokens(tokens) — пишет refresh_token + expires_at
   - fetchAuthMe() → applyBootstrapFromAuthMe(access, me)
       сохраняет phone, name, role, id, pages, hidden_pages в localStorage
   - localStorage.removeItem('Passport') — очистка legacy ключа
   - scheduleProactiveOidcRefresh(onRefreshed)
   - navigateTo('/') replace
6. на ошибке: показывает текст и ссылку на /auth
```

### 6.5 Хранение токенов

| Ключ | Где | Что |
|---|---|---|
| `access_token` | `localStorage` | Текущий JWT (используется во всех axios-запросах как `Bearer`) |
| `oidc_refresh_token` | `localStorage` (rusaifin) / `secureStorage` (rusaisklad — обёртка) | Refresh token |
| `oidc_access_expires_at_ms` | `localStorage` | epoch ms истечения access_token (берётся из JWT `exp` или `expires_in`) |
| `pkce_verifier`, `pkce_state` | `sessionStorage` | Только во время authorize → callback |
| `user_role_string` | `localStorage` | Закодированная строка роли (см. middleware) |
| `user_pages`, `user_hidden_pages`, `user_pages_timestamp` | `localStorage` | Навигационная карта по ролям |

⚠️ **Безопасность:** хранение access_token в `localStorage` — XSS-уязвимо. Это принятый компромисс ради SPA-простоты, но любой `<script>` в DOM получает токены целиком. Долгосрочно — рассмотреть httpOnly-cookie + BFF-pattern, особенно если будет вход через third-party content.

### 6.6 Refresh-логика (`oidcRefresh.ts`)

**Single-flight** — гарантия одного активного refresh:

```ts
let refreshPromise: Promise<string | null> | null = null
async function tryRefreshOidcAccessToken() {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {...})()
  try { return await refreshPromise } finally { refreshPromise = null }
}
```

**Proactive refresh** — таймер за 5 минут до exp:

```ts
const RENEW_BEFORE_MS = 5 * 60 * 1000
const delay = Math.max(10_000, expMs - RENEW_BEFORE_MS - Date.now())
setTimeout(...)  // обновляет access_token, перепланирует себя же
```

**Reactive refresh** — на 401 (предполагается, но в показанных файлах явный axios-interceptor не виден — нужно сверить с `src/shared/api/http`).

### 6.7 OIDC-конфиг dev окружения

| Параметр | rusaifin-front | rusaisklad-front |
|---|---|---|
| `oidcIssuer` | `https://dev.sso.rusaifin.ru` | `https://dev.sso.rusaifin.ru` |
| `oidcClientId` | `019df247-8dd3-73bf-8f0d-58b742672c22` | `019df247-8dd8-72c3-a251-9d824cf77370` |
| `oidcRedirectUri` | `https://dev.fintech.rusaifin.ru/auth/callback` | `https://dev.rusaisklad.ru/auth/callback` |
| `oidcScopes` | `openid profile email phone fieldsales.read fieldsales.write` | `openid profile email phone inventory.read inventory.write` |

Конфиг прокидывается через Nuxt `runtimeConfig.public` из env-переменных `NUXT_PUBLIC_OIDC_*`.

### 6.8 Consent flow (KYC, опциональный)

Помимо OIDC, фронт rusaifin реализует отдельный **consent-session** flow для сбора паспортных данных и согласий (КYC). Endpoints:

```
GET  /api/consent-session/:token
POST /api/consent-session/:token/phone
PUT  /api/consent-session/:token/profile
POST /api/consent-session/:token/sms/send
POST /api/consent-session/:token/sms/verify
POST /api/consent-session/:token/flow/renew
GET  /api/consent-session/:token/prefill
POST /api/consent-session/:token/complete
```

Триггерится через query-параметр `?consent_token=...` на главной странице — middleware редиректит на `/consent/<token>`. Это **не часть OAuth flow**, а отдельная фича для прохождения профиля. Состояния: `created → opened → awaiting_profile → sms_sent → sms_verified → profile_saved → consented → redirected → completed | expired`.

---

## 7. Тесты

| Сервис | Trait для feature-тестов с OAuth |
|---|---|
| rusaifin / rusaisklad | `Tests\Feature\Concerns\AuthenticatesAsOAuthUser` |
| rusaicore | `WithDefaultOAuthUser` + `AuthenticatesOAuth` |
| rusaisklad legacy | `tests/Feature/AuthTest` (Sanctum) — скипнуты, переписать через trait при необходимости |

---

## 8. Документация v2 (canonical)

`rusaicore/docs/russmarket360/`:

| Файл | О чём |
|---|---|
| `00-overview.md` | Карта сервисов |
| `01-identity-access-rusaiauth.md` | OAuth2/OIDC спека rusaiauth |
| `04-cutover-playbook.md` | Phase 1/2/3 cutover |
| `07-implementation-roadmap.md` | M0–M5 milestones |
| `frontend-handoff.md` | Спека для фронта (OIDC discovery, client_id'ы, PKCE, scopes) |

---

## 9. Текущий статус (snapshot 2026-05-04, до prod-cutover)

> Этот раздел — состояние на момент сборки конспекта. Актуальный статус и открытые риски — см. `russ360-audit-2026-05-18.md`.

### ✅ Сделано (на 2026-05-04)

- **Dev cutover завершён 2026-05-04** — все 4 backend-сервиса и оба фронта на dev переведены на OAuth.
- 10 ключевых граблей решены (см. §5.7).
- Stage 5 backfill `identity_users` — на dev сделан, mapping ролей задокументирован (memory `backfill_state.md`).
- Frontend PKCE-клиенты в обоих Nuxt-фронтах:
  - `oidcPkce.ts` (генерация + authorize redirect + token exchange)
  - `oidcRefresh.ts` (proactive scheduler + single-flight refresh)
  - `/auth/callback` route с CSRF-state-check
  - bootstrap через `/api/auth/me`

### 🚧 Что предстоит сделать до prod-cutover

#### 9.1 rusaiauth UI — главный незакрытый блок

У rusaiauth **нет полноценного UI**. На сегодня есть:

- `resources/views/auth/login.blade.php` — голая Blade-форма с inline-CSS на 50 строк.
- `resources/views/auth/authorize.blade.php` — минимальный consent screen.
- `welcome.blade.php`.
- API в `routes/api.php`: `Admin\UserController` (CRUD юзеров + assign global role) и `Auth\LoginController` (password / OTP request / verify) — **бэкенд есть, UI поверх него отсутствует**.

**Чего нет:**

- Admin-панели: users / roles / permissions / OAuth-clients / consents / OTP / sessions.
- Self-service UI: профиль, смена пароля, мои consents, активные токены, 2FA.
- Восстановления пароля (ни UI, ни API).
- Общего layout / стилей.

**Список фич (входит/не входит в MVP):**

| Фича | Статус | Замечания |
|---|---|---|
| Login: phone/email + пароль | ✅ есть | дизайн надо |
| OTP-логин (SMS / email) | ⚠️ API есть, UI нет | для прода нужен SMS-провайдер; для dev — log-channel |
| Восстановление пароля | ❌ нет (ни UI, ни API) | стандартный Laravel password broker + email |
| Регистрация | ❌ нет | SSO обычно без неё, юзеров создают админы — подтвердить |
| Consent screen | ✅ минимальный | для prod: «не показывать снова», иконки клиентов |
| Logout | ✅ есть | OK |
| Profile / смена пароля / привязка телефона | ❌ нет | решить, нужно ли |
| Управление сессиями / revoke токенов | ❌ нет | решить, нужно ли |
| MFA / TOTP | ❌ нет | решить, нужно ли |
| i18n (ru/en) | ❌ только ru | для прода — ok |
| A11y, mobile UX, error states | ❌ | для прода — обязательно |

**Выбор стека (открыт):**

| Вариант | Плюсы | Минусы | Время |
|---|---|---|---|
| **A. Blade + Alpine.js** (продолжение текущего) | Никаких новых зависимостей, серверный SSR, простой деплой | Не SPA-style, ограниченная интерактивность | 2-3 дня min, неделя prod-ready |
| **B. Inertia + Vue 3** | Vue-стек как в SPA, без отдельного билда на фронте | Vite в rusaiauth, новый Dockerfile с node | 3-4 дня |
| **C. Отдельный Nuxt SPA на `auth.dev.sso.rusaifin.ru`** | Полная свобода фронта, тот же стек что у rusaifin/rusaisklad | Отдельный репо/билд/деплой/CORS | неделя+ |

Также как опции — **Filament 3** (готовая admin-панель «за пару часов» для управления юзерами/клиентами/consents), **Livewire/Volt** для self-service.

**Рекомендация:** A для dev → пересмотреть к prod-cutover.

**4 открытых вопроса:**
1. Стек — A, B, C, или Filament для admin-части?
2. Scope — минимум (login + OTP + password reset + consent) или полный (+ profile, sessions, MFA)?
3. Дизайн — макеты от дизайнера или функциональный без украшательств?
4. SMS-провайдер для OTP — есть ли подключённый, или для dev log-канал?

#### 9.2 Прочие задачи до prod-cutover

- **Backfill `identity_users` на проде** — mapping ролей сверять перед `--write` (см. memory `backfill_state.md`).
- Зарегистрировать **prod OAuth-клиенты** в rusaiauth для prod-доменов фронтов; поменять `oidcClientId` и `oidcRedirectUri` в env обоих фронтов.
- Prod-домены: подтвердить `sso.rusaifin.ru` HTTPS / TrustProxies.
- Свежевыпущенные prod-токены: проверить наличие `iss` claim после деплоя rusaiauth.
- Cutover-миграции прогнать только в окне cutover (`php artisan migrate --path=database/migrations/cutover`).
- Frontend-handoff для prod: фронты ходят на `sso.rusaifin.ru`, redirect_uri'ы зарегистрированы в Passport-clients, scopes идентичны dev.
- Sanctum-тесты `tests/Feature/AuthTest` в rusaisklad — переписать через `AuthenticatesAsOAuthUser` или окончательно скипнуть.
- Реактивный 401-handler / axios-interceptor — проверить что во всех фронтах есть retry с `tryRefreshOidcAccessToken()` на ответ 401, иначе истечение токена выкидывает на /auth даже если refresh ещё валиден.
- **Безопасность токенов в `localStorage`** — стратегическое решение: оставить как есть (компромисс) или переезжать на httpOnly cookie + BFF-pattern.
- Прод-fronts (`fintech.rusaifin.ru`, `rusaisklad.ru`) — на момент снимка ещё на legacy api_token; после cutover'а нужно собирать билд `Dockerfile.front.prod` с обновлёнными env и публиковать.

---

## 10. Полезные команды (read-only)

```bash
# Прод (после явного «иди на прод»):
ssh root@82.146.57.149

# rusaiauth: проверить iss в свежем токене (на dev)
docker exec rusaiauth_back_dev-app php /var/www/html/scripts/mint-smoke-token.php <user_uuid> <client_name> <scopes>

# Поднять локально все 4 backend
docker compose -f rusaiauth/compose.yml up -d
docker compose -f rusaicore/compose.yml up -d
docker compose -f rusaifin/compose.local.yml up -d
docker compose -p rusaisklad_back_local -f rusaisklad_back/compose.back.local.yaml up -d

# Прогнать cutover-миграции (НЕ запускаются обычным migrate)
php artisan migrate --path=database/migrations/cutover

# Backfill identity_users (dev пройден; prod — сначала dry-run)
# (см. backfill_state.md memory для точной команды и mapping)
```

---

## 11. Что сюда стоит добавить позже (известные пробелы)

- Точный axios-interceptor: где именно срабатывает refresh на 401, есть ли retry-queue для concurrent-запросов.
- Spec rusaisklad `secureStorage` обёртки — какой именно шифр используется для refresh_token и где ключ.
- Точный список prod OAuth-клиентов в `rusaiauth` (после регистрации).
- ER-диаграмма rusaicore (Employee, Project, OperationalLocation, ProjectMembership) — чтобы не лезть в код каждый раз.
- Реверб (rusaifin-ws): какие каналы, как авторизуется presence-channel при OAuth-токене.

---

## 12. Что произошло после snapshot'а 2026-05-04 (краткая хронология до 2026-05-18)

| Дата | Событие | Источник |
|---|---|---|
| 2026-05-08 | M2 Phase 1+2 smoke зелёный локально, 14 багов разобраны; локальный backfill identity_users; rusaisklad backfill dry-run | memory `m2_phase1_smoke_done`, `m2_phase2_done`, `m2_local_identity_backfill`, `m2_rusaisklad_backfill_dryrun` |
| 2026-05-08 | M2.1 публичная регистрация переехала из rusaifin в rusaiauth | memory `m2_1_registration_done` |
| 2026-05-12 | Production cutover runbook готов | memory `cutover_ready_2026-05-12` |
| **2026-05-13** | **Prod-cutover окно успешно пройдено. OAuth на проде.** 11 граблей зафиксированы. | memory `m2_prod_cutover_done` |
| 2026-05-13 | Post-cutover hotfixes: QR refresh, slow /api/staff/result (admin + non-admin), Stage 1 миграция projects+memberships добита, unrestricted roles 409 fix, Stage 1 миграция (projects+memberships) | memory `reverb_qr_refresh_postcutover`, `staff_result_perf`, `staff_result_perf_nonadmin`, `stage1_memberships_missing`, `unrestricted_roles_memberships` |
| 2026-05-13 | Refresh dev←prod pipeline (`/root/refresh-dev-from-prod.server.sh`) | memory `refresh_dev_from_prod_2026-05-13` |
| **2026-05-18** | Stage 1 закрыт: 243/243 локаций rusaifin зеркалированы в `rusaicore.operational_locations`; `project_points.core_location_external_id` заполнено (но write-only — читателей пока нет). 4 inactive проекта зеркалированы. | memory `stage1_locations_mirrored_2026-05-18` |
| 2026-05-18 | Сводный аудит: `docs/russ360-audit-2026-05-18.md` — `P0` (logout без revoke на обоих фронтах, dual-read Memberships в rusaifin), `P1` (Stage 2 — переключение читателей, 112+ мест читают `$user->role_id`), `P2` (минор). | `russ360-audit-2026-05-18.md` |

### Открытые P0 на 2026-05-18

1. **Logout не ревокирует OAuth токены на IdP** на обоих фронтах. После «Выйти» refresh_token остаётся валидным до истечения TTL. Fix: вызывать `performGlobalOidcLogout()` в `oidcAuthAdapter.logout()`.
2. **Двойное чтение Memberships в rusaifin** — `StaffVisibilityScopeService` читает Core gateway + raw SQL в legacy таблицы параллельно. Любой write через Core без зеркала в legacy = расхождение видимости агентов.

### Stage 2 (план, не начат)

После Stage 1 backfill локаций — переключение читателей с локального `Point`-Eloquent на `OperationalLocationCatalog` контракт. После — выпиливание legacy чтений в `StaffVisibilityScopeService` и `PointService::attachAgent/detachAgent`.
