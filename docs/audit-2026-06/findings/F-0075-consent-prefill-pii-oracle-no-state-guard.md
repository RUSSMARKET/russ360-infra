---
id: F-0075
flow: product-consent
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`GET /consent-session/{token}/prefill` отдаёт ПОЛНЫЕ расшифрованные ПД клиента (паспорт серия/номер, адрес регистрации, ФИО, ДР) по одному токену, без проверки статуса сессии, и продолжает их отдавать даже после терминальных переходов (`complete`/`redirect`) — весь 2-часовой TTL сессии.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Product/ConsentSessionController.php:409-417` — `prefill()` не проверяет статус, просто `getSessionByToken($token)` → `buildPostSmsPayload($session)`.
- `rusaifin/app/Services/ProductConsent/ProductConsentService.php:217-248` — `buildPostSmsPayload()` гейтит ТОЛЬКО на `if (!$session->sms_verified_at) throw` (219); для complete/renew/confirm-flow кладёт `$profile?->toPrefillArray()` (242,244).
- `CustomerProfile::toPrefillArray()` возвращает расшифрованные паспортные ПД (passport_series/number, registration_address и т.д.).
- `…/ProductConsentService.php:311-316` — `complete()` НЕ сбрасывает `sms_verified_at`; `prefill`/`buildPostSmsPayload` не вызывают `assertSessionCanMutate`, поэтому `completed`/`redirected`/`consented` сессия всё ещё выдаёт полный prefill.

## Триггер / repro
Утечка/перехват токена сессии (referer-leak при редиректе на downstream_url, история браузера shared-устройства, лог-прокси) после первого успешного `sms/verify` → `GET /consent-session/{token}/prefill` отдаёт полный паспорт клиента до истечения TTL, в том числе уже после завершения flow.

## Корневая причина (гипотеза)
Нет инвалидации `sms_verified_at` после терминальных переходов и нет отдельного короткого TTL на «окно prefill»; полный prefill-доступ живёт столько же, сколько сессия. Токен сильный (`Str::random(80)`, не перечислим) — поэтому P2, а не P1: требуется компрометация токена, не happy-path IDOR.

## Радиус поражения
Раскрытие паспортных ПД одного клиента на сессию при компрометации соответствующего токена; окно — до 2 ч и переживает завершение flow.

## Направление фикса
Сбрасывать/помечать `sms_verified_at` при `complete`/`redirect`; ограничить окно prefill коротким TTL после verify; не отдавать `toPrefillArray` в терминальных статусах.
