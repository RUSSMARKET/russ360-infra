---
id: F-0112
flow: motivation
dimension: data-integrity
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Для компенсаций и BringFriend не сохраняется, кто из руководителей начислил сумму (нет `from_user_id`), в отличие от Penalties — нет следа для расследования спорных начислений.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Motivation/PenaltiesController.php:130` — `$validated['from_user_id'] = $user->id`.
- `CompensationController::addUserCompensations` (`:121-128`) и `BringFriendController::addUserBringFriend` (`:121-128`) — такого нет; в их таблицах столбца `from_user_id` нет (миграция `:23-37`).

## Триггер / repro
Начисление компенсации/реферала → в записи нет, кто начислил.

## Корневая причина (гипотеза)
Непоследовательность аудит-полей между сущностями мотивации. Деньги начисляются корректно — только пробел в аудит-трейле.

## Радиус поражения
Аудит-трейл компенсаций/рефералов.

## Направление фикса
Добавить `from_user_id` в обе таблицы и проставлять при начислении.
