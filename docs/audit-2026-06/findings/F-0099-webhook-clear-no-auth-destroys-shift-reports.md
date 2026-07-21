---
id: F-0099
flow: webhooks
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaifin]
status: closed
---

## Симптом
`GET /api/webhook/<secret>/clear/?id=<user_id>` без аутентификации удаляет все `ShiftReport` последней смены произвольного пользователя. Аутентификация = знание статичного секрета в URL (попадает в access-логи/Referer/историю). Нет HMAC, нет валидации `id`.

## Доказательства (file:line)
- `rusaifin/routes/api.php:549` — `webhook/12093456087jenfrclearnwe95tgh/clear/` БЕЗ middleware, секрет захардкожен в пути.
- `rusaifin/app/Http/Controllers/WebhooksController.php` `clearArtem`:
  - `$user_id = $_GET['id'];` — нет валидации, нет auth.
  - `$shift = Shift::where('user_id',$user_id)->orderBy('id','desc')->first();` затем `$shift->end_time = null;` — если у юзера нет смен, `$shift===null` → fatal 500.
  - `$shift->end_time = null;` присваивается, но НИКОГДА не сохраняется (нет `->save()`).
  - `return ShiftReport::where('shift_id',$shift->id)->delete();` — отчёты смены удаляются.

## Триггер / repro
`GET /api/webhook/12093456087jenfrclearnwe95tgh/clear/?id=<любой_user_id>` → удаляются ShiftReport последней смены этого юзера, без токена. Перебор последовательных `id` → массовый wipe отчётов.

## Корневая причина (гипотеза)
Аутентификация вебхука = статичный секрет в URL (логируется прокси/nginx/Referer); нет HMAC/привязки к вызывающей системе; нет валидации `id`; забытый `->save()` + null-guard.

## Радиус поражения
Целостность отчётов смен; потенциальный массовый wipe перебором целочисленных `id`.

## Направление фикса
Проверка секрета через `hash_equals` из заголовка/конфига (не из URL); валидация `id` (`exists:users,id`); null-guard на `$shift`; читать через `$request`, не `$_GET`. См. F-0100 (общий класс webhook-auth).

## Статус закрытия

Закрыто коммитом `5979d29` (rusaifin), проверено по коду на `origin/main` 2026-07-21.
`clearArtem` перешёл на `$request->validate` с `exists:users,id` вместо `$_GET`.
