# ADR-0008: BFF для fintech (login-only OIDC → серверная сессия)

- Статус: Accepted (реализация: Phase 0 — бэкенд за флагом, 2026-06-29)
- Связано: [[login-failure-taxonomy-2026-06]], [[rusaifin-401-error-codes]], ADR-0001 (OAuth/OIDC)

## Контекст

fintech — статический Nuxt-SPA, **публичный OAuth2/OIDC PKCE-клиент**: браузер сам
хранит токены (localStorage) и PKCE-verifier (sessionStorage/localStorage/cookie),
протаскивая verifier через внешний редирект на SSO.

По телеметрии прода (см. login-failure-taxonomy-2026-06) это даёт системный отказ
входа **#1**: verifier вытесняется к моменту возврата на `/auth/callback`
(`auth_callback_failure`, `hasVerifier:false`) — у **~20-40 РАЗНЫХ пользователей/день
во ВСЕХ браузерах** (Safari iOS, **Яндекс.Браузер**, Chrome). Воронка `authorize→token`
≈ 17%. Клиентские костыли (loop-breaker, cookie-слой, backup-verifier) петлю гасят,
но конверсию не чинят.

## Ключевой факт, определивший дизайн

rusaifin ходит в rusaicore по **своему `client_credentials` service-токену**
(`CoreApiClient` → `OAuthClientCredentialsTokenProvider`), а **НЕ** пробрасывает токен
пользователя. Контроллеры читают `$request->user()` → `App\Models\User\User` (НЕ
завязаны на JWT-гвард: 0 использований `auth()->user()`, 22× `$request->user()`,
112× `->role_id`).

**Следствие:** токен пользователя нужен только чтобы опознать его при логине.

## Решение

**rusaifin становится BFF для своего SPA. OIDC — механизм логина, дальше обычная
Laravel-сессия.** Нового сервиса нет.

- **Server-side PKCE**: verifier генерится и живёт в серверной сессии, в браузер не
  попадает → чинит `no_payload`.
- **Login-only**: после обмена кода `OAuthTokenValidator::validate($accessToken)` даёт
  `sub` → `User`; `Auth::guard('web')->login`; токены **выбрасываются** (Core держится
  на service-credential). Хранилища/рефреша токенов на сервере НЕТ.
- **First-party HttpOnly cookie** на `fintech.rusaifin.ru` через существующий
  same-origin `/api`-прокси → переживает Safari ITP.
- **Гвард `web` (session) вместо `oauth` (JWT)**, возвращает тот же
  `App\Models\User\User` → **~200 контроллеров не меняются**.
- Включение за флагом `BFF_AUTH_ENABLED`; режим `oidc` остаётся для отката.

## Что это удаляет (выигрыш «без лишнего»)

Клиентские костыли после ретайра `oidc`: `auth-early-redirect.js`, 3-слойный
PKCE-persist + loop-breaker (`oidcPkce.ts`), `oidcRefresh.ts` (хранение токенов,
proactive refresh, cross-tab), `tokenStorage/accessToken`, `no_payload`-стадии
callback, и т.д. (~1500+ строк).

## Tier-3, поглощённый BFF

- Multi-tab refresh-rotation — исчезает (нет клиентских токенов, одна серверная сессия).
- Отзыв токена при disable — действует сразу (session + `UserIsNotDisabled` per-request),
  не до exp ≤1ч.
- (Standalone, вне BFF: phone-normalization в password-sync; OTP lockout UX.)

## Последствия / риски

- Вводим cookie-сессию + CSRF в ранее stateless API (только новая stateful-группа).
- `online_in` и identity-lookup переносятся из JWT-замыкания в login/middleware.
- Два режима auth сосуществуют на время миграции (гварды раздельны).
- `App\Models\User::class` в `config/auth.php` был несуществующим → исправлено на
  `App\Models\User\User::class` (критично для session-гварда).

## Метрика успеха

Воронка `authorize→session` ≈ 100% (vs 17%); `auth_callback_failure`→~0; в браузере
нет токенов; контроллеры не тронуты; костыли удалены.
