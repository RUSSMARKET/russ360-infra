---
id: F-0096
flow: chats
dimension: data-integrity
severity: P3
confidence: likely
services: [rusaifin]
status: open
---

## Симптом
`addUsers` слепо создаёт `ChatUser` для каждого id из запроса без `exists`-валидации и без dedup → можно добавить одного юзера N раз (дубли pivot) или несуществующего user_id.

## Доказательства (file:line)
- `rusaifin/app/Services/Chats/ChatService.php:142-152` — `foreach($users as $user){ ChatUser::create(['chat_id'=>..., 'user_id'=>$user]); }` без `exists`, без проверки дубля.
- Зависит от правил `AddChatUsersRequest` (не верифицировано детально) → confidence likely.

## Триггер / repro
`POST /api/chats/{id}/users` с повторяющимися/несуществующими user_id → дубли строк `chat_users` или висячие ссылки.

## Корневая причина (гипотеза)
Нет валидации входного списка и нет UNIQUE(chat_id,user_id).

## Радиус поражения
Целостность состава участников чата; усугубляется F-0095 (любой может дёргать addUsers на чужом чате).

## Направление фикса
Валидировать `users.*` через `exists:users,id`; `syncWithoutDetaching` либо UNIQUE(chat_id,user_id).
