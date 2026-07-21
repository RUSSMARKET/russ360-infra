---
id: F-0095
flow: chats
dimension: correctness
severity: P0
confidence: confirmed
services: [rusaifin]
status: closed
---

## Симптом
Любой авторизованный не-админ пользователь может переименовать, удалить, добавить/удалить участников и просмотреть список участников ЛЮБОГО чата по id, не будучи его участником. Утечка PII участников (ФИО, телефон, email) + порча/удаление чужих чатов. Обход authz на happy-path.

## Доказательства (file:line)
- `rusaifin/app/Services/Chats/ChatService.php:28-37` — конструктор при `!chatHasAccess()` делает `return null;`. **Возврат из `__construct` в PHP игнорируется** → `new ChatService(...)` ВСЕГДА возвращает валидный объект.
- `ChatService.php:82` `update()`, `:92` `delete()`, `:127` `getUsers()`, `:142` `addUsers()`, `:160` `deleteUsers()` — НЕ вызывают `chatHasAccess()` повторно.
- `ChatService.php:127-132` `getUsers()` — `select(['users.id','name','surname','patronymic','phone','email'])` → PII участников.
- `rusaifin/app/Http/Controllers/Chats/ChatController.php:172-176, 219-223, 273-279` — `$chat = new ChatService($chat_id, $user); if($chat) { $chat->update()/delete()/getUsers(); }` — `if($chat)` всегда true (это `new`-объект).
- `rusaifin/routes/api.php:274,275,278,279,280` — роуты под `['auth:oauth', UserIsNotDisabled::class]` (любая роль, без chat-membership/admin gate).
- Контраст: `getMessages()`/`messageHasAccess()` корректно перепроверяют — защита есть только на сообщениях, не на самом чате/участниках.

## Триггер / repro
Залогиниться обычным агентом (не creator, не участник, не admin):
- `PUT /api/chats/{любой_id}` `{"name":"hacked"}` → 200, чат переименован.
- `DELETE /api/chats/{любой_id}` → чат soft-удалён.
- `GET /api/chats/{любой_id}/users` → JSON с ФИО/телефоном/email всех участников (перебор id → массовая выгрузка PII).
- `POST/DELETE /api/chats/{любой_id}/users` → подмена состава участников.

## Корневая причина (гипотеза)
Попытка использовать конструктор как guard через `return null` — антипаттерн, в PHP не работает; объект всё равно полностью сконструирован. Авторизация не enforce'ится в мутирующих методах сервиса (в отличие от message-путей).

## Радиус поражения
Все чаты системы; утечка PII участников + порча/удаление чатов любым авторизованным пользователем. **P0 — обход authz на happy-path + PII-утечка.**

## Направление фикса
Конструктор должен БРОСАТЬ исключение (или контроллер явно вызывать `$chat->chatHasAccess()` → 403). Каждый мутирующий метод (`update/delete/addUsers/deleteUsers/getUsers`) guard'ить через `chatHasAccess()`, как уже сделано в `getMessages()`.

## Статус закрытия

Закрыто коммитом `5979d29` (rusaifin), проверено по коду на `origin/main` 2026-07-21.
Антипаттерн `return null` в конструкторе убран; `chatHasAccess()` вызывается во всех мутирующих методах (update/delete/getUsers/addUsers/deleteUsers).
