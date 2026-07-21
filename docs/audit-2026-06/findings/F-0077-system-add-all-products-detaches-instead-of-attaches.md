---
id: F-0077
flow: products-catalog
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Эндпоинт «массово прикрепить все продукты ко всем агентам» (`GET /api/system/add-to-all-agents-all-products`) на деле **открепляет** все продукты у всех агентов и руководителей групп и при этом рапортует «Продукты успешно прикреплены». Один admin-GET стирает все привязки `user_products` всего полевого штата.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/System/SystemController.php:374` — `$users = User::whereIn('role_id', [3, 10])->get();` (все агенты role 3 + тимлиды role 10).
- `…/SystemController.php:402-403` — комментарий «Используем syncWithoutDetaching чтобы избежать дублирования», но код: `$user->products()->detach($productIds);` (деструктивное открепление вместо прикрепления).
- `…/SystemController.php:405` — `$totalAttachments += count($productIds);` — счётчик «прикреплений» считает откреплённое.
- `…/SystemController.php:411` — ответ `'message' => 'Продукты успешно прикреплены к пользователям'`.
- `rusaifin/routes/api.php:492` — роут под `CheckPermission:admin`.

## Триггер / repro
Админ вызывает `GET /api/system/add-to-all-agents-all-products` (ожидая массовую привязку) → у всех агентов и РГ снимаются ВСЕ привязки `user_products`, ответ 200 «успешно прикреплены». Никакого восстановления — это `detach`, не upsert.

## Корневая причина (гипотеза)
Опечатка/копипаст: вместо `syncWithoutDetaching($productIds)` (что соответствует комментарию и имени метода) написан `detach($productIds)`. Деструктивная операция под видом аддитивной; ответ и счётчик не отражают факт.

## Радиус поражения
Все агенты (role 3) и руководители групп (role 10) системы — массовая потеря привязок продукт↔агент одним admin-действием. Транзакция (`DB::transaction`, 400) не спасает — она коммитит именно открепление.

## Направление фикса
Заменить `detach($productIds)` на `syncWithoutDetaching($productIds)`; исправить счётчик `total_attachments` на фактически добавленные и текст ответа.

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`SystemController:403` по-прежнему `detach($productIds)` под комментарием про `syncWithoutDetaching`, ответ рапортует «успешно прикреплены».
