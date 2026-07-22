---
id: F-0122
flow: identity-status-sync
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaifin, rusaiauth]
status: open
---

## Симптом

Пользователь активен в rusaifin (`users.disabled=0`, `deleted=0`, привязан к точке), но не может войти: экран отдаёт «Доступ к аккаунту ограничен. Обратитесь в поддержку». Причина — рассинхрон: в rusaiauth `identity_users.status='disabled'`, а логин проверяет **только** этот статус. В rusaifin юзер выглядит здоровым, саппорт починить не может и диагноза не видит.

На 2026-07-22 в проде было **6 таких рассинхронов** (Исаева 153, Сорокина 287, Ганченко 351, Бутусов 355, Гасанов 387, Садыков 402) + ранее Амиров 196. Разблокированы вручную (`identity_users.status → active`). Два кейса (Амиров, Сорокина, обращения саппорта) пришли независимо друг от друга — проблема воспроизводится в проде, не разовая.

## Доказательства (file:line)

- `rusaiauth/app/Http/Controllers/Auth/LoginController.php:56` и `:107` — и password-, и otp-логин отбивают вход единственной проверкой `if ($user->status !== 'active')`. Никакой сверки с rusaifin.
- `rusaifin/app/Services/User/UserService.php:231-252` (`syncIdentityAccountStatus` + `resolveIdentityAccountStatus`) — обратный пуш статуса в rusaiauth (`/internal/v1/users/set-status`) вызывается **только** из `UserService::disable()` (`:204`) и `UserService::delete()` (`:184`).
- `rusaifin/app/Services/User/UserService.php:208-227` — HTTP-пуш `setStatus()` находится **внутри** `DB::transaction()`. Откат транзакции после успешного HTTP → rusaiauth изменён, rusaifin откачен, откатить HTTP-побочку нельзя (тот же паттерн «HTTP-в-транзакции» из findings_log).
- `rusaifin/app/Console/Commands/RemoveUnregisteredUsers.php:30-32` — крон сносит юзеров через `User::where(...)->delete()` (query builder, в обход `UserService::delete()`) → sync не вызывается вообще.
- Прямые правки в БД/tinker/сиды — тоже мимо sync.

## Триггер / repro

Разблокировка/изменение статуса юзера любым путём, кроме `UserService::disable()/delete()` (крон-очистка, прямой SQL, откат транзакции после успешного пуша, любой сид), оставляет `identity_users.status` в старом значении. При `disabled` → вечное «обратитесь в поддержку» на входе.

Доказанный пост-cutover кейс: Сорокина Ульяна (287, `79531594457`). 2026-07-10 её разблокировали (запись в `history` есть), а 2026-07-14 16:23:52 MSK `identity_users.status` ушёл в `disabled` — **без записи в history**, бесследно. То есть рассинхрон возник уже после M2, не наследие импорта.

## Корневая причина (гипотеза)

Логин доверяет `identity_users.status` как единственному источнику правды, но синхронизация этого поля из rusaifin (владельца статуса блокировки) частичная: покрыты только два метода сервиса, а HTTP сидит в транзакции. Нет ни идемпотентной сверки, ни алерта на расхождение. Симметричная запись `active` при разблокировке теряется на любом пути мимо `UserService`.

## Радиус поражения

Полная потеря доступа для активного сотрудника, невидимая для саппорта (в rusaifin всё зелёное). Копится молча, всплывает только через обращения. P1: блокирует работу полевого персонала, диагностируется только прямым SQL в rusaiauth.

## Направление фикса (не реализовано)

1. Вынести HTTP-пуш `setStatus()` из `DB::transaction()` в `afterCommit`-хук (устранить рассинхрон при откате).
2. Провести любую смену `disabled`/`deleted` (включая `RemoveUnregisteredUsers` и прочие query-builder пути) через единую точку, дергающую sync.
3. Добавить консольную команду-сверку `identity_users.status` ↔ rusaifin `users.disabled/deleted` с отчётом и опциональным `--write`; повесить на расписание + алерт при расхождении. Она же закроет будущие накопления.

## Проверка статуса

**2026-07-22 — сверено с продом.** Дефект на месте: `LoginController.php:56/107` (только `status !== 'active'`); `UserService.php:208-227` (HTTP в транзакции); `RemoveUnregisteredUsers.php:30-32` (delete мимо sync). 6 рассинхронов найдены и вручную разблокированы.

**2026-07-22 — фикс реализован на `dev` (НЕ на проде).**
- rusaiauth `55ef583`: read-only endpoint `POST /internal/v1/users/status-audit`.
- rusaifin `9147943`: HTTP-пуш вынесен в `DB::afterCommit` (disable/delete); `RemoveUnregisteredUsers` пушит `deleted` до hard-delete; команда `identity:reconcile-status {--write}`; расписание hourly report-only + алерт `identity.status_drift_detected` в oauth-лог.
- Проверено локальным dry-run: команда достучалась до endpoint, поймала реальный дрейф, отрисовала отчёт.
- **Порядок деплоя: сначала rusaiauth (endpoint), потом rusaifin (команда), иначе `status-audit` → 404.**
- Остаётся **open** до деплоя на прод и первого чистого прогона реконсилятора.
