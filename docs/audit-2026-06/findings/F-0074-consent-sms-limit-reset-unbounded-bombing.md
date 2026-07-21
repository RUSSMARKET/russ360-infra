---
id: F-0074
flow: product-consent
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin, fintech]
status: closed
---

## Симптом
Единственный анти-абьюз потолок на отправку реальных SMS (`SMS_SEND_LIMIT = 3` на сессию) обнуляется при каждом вызове публичного `POST /consent-session/{token}/phone`. В сочетании с полным отсутствием HTTP-throttle это даёт неограниченную отправку реальных SMS на произвольный, выбираемый вызывающим номер от имени бренда «РУССАЙФИН».

## Доказательства (file:line)
- `rusaifin/app/Services/ProductConsent/ProductConsentService.php:100` — `resolvePhone()` в `update([...])` ставит `'sms_send_attempts' => 0` (сброс счётчика при каждой смене телефона).
- `…/ProductConsentService.php:125-127` — единственная проверка лимита: `if ($session->sms_send_attempts >= self::SMS_SEND_LIMIT) throw …`.
- `…/ProductConsentService.php:88,131` — телефон берётся из тела запроса (`'phone' => $phone`) и реально отправляется: `MTSService::sendSms($session->phone, …)`.
- `rusaifin/routes/api.php:76-77` — `consent-session/{token}/phone` и `…/sms/send` без `auth` и без `throttle`.
- `rusaifin/bootstrap/app.php` — `withMiddleware()` НЕ добавляет `throttle` к группе `api`; на роутах consent тоже нет `throttle` (`grep throttle routes/api.php` пусто).

## Триггер / repro
Имея один валидный публичный токен сессии (выдаётся легально при инициации flow), в цикле:
`POST /consent-session/{token}/phone {phone: <жертва>}` → `POST /consent-session/{token}/sms/send` → повтор.
Каждая итерация сбрасывает `sms_send_attempts` в 0 и отправляет 1 реальную SMS на выбранный номер. Верхнего предела нет (ни per-session, ни per-IP, ни per-phone). Toll fraud + SMS-флуд на чужой номер.

## Корневая причина (гипотеза)
Сброс anti-abuse счётчика отправок внутри `resolvePhone` (счётчик логически привязан к телефону, а не к сессии) + полное отсутствие rate limiting на публичной consent-группе. Известный общий тезис аудита 2026-05-18 «нет rate limiting» здесь конкретизируется: даже существующий per-session лимит defeated собственным сбросом.

## Радиус поражения
Биллинг за SMS (MTS), репутация отправителя/sender-id, харассмент произвольных номеров от имени бренда. Любой, кто может инициировать consent-сессию.

## Направление фикса
Не обнулять `sms_send_attempts` в `resolvePhone` (вести счётчик отправок независимо от смены телефона) + `throttle` на `/phone` и `/sms/send` по комбинации token+IP+phone.

## Статус закрытия

Закрыто коммитом `5979d29` (rusaifin), проверено по коду на `origin/main` 2026-07-21.
Сброс `sms_send_attempts` убран: счётчик только инкрементируется (ProductConsentService:140), лимит проверяется (:124).
