---
id: F-0051
flow: transfer-documents
dimension: architecture-drift
severity: P3
confidence: confirmed
services: [rusaisklad_back]
status: open
---
## Симптом
Контроллер `uploadSenderDocument` собирает файлы напрямую (`file`/`files`), не используя `getFiles()`, тогда как receiver/admin-эндпоинты поддерживают альтернативные ключи (`document`, `receiver_file`, `attachment`). Несогласованный контракт между sender и receiver upload: один и тот же ключ работает для receiver и даёт 422 для sender.

## Доказательства (file:line)
- `app/Http/Controllers/API/Inventory/InventoryDocumentController.php:~200-202` — sender: `$files = $request->hasFile('files') ? $request->file('files') : [$request->file('file')]`.
- `:~258` (receiver) и `:~321` (admin-attach) используют `$request->getFiles()` (UploadReceiverDocumentRequest) с `SINGLE_FILE_KEYS = ['file','document','receiver_file','attachment']`.
- `UploadSenderDocumentRequest` валидирует только `file`/`files`, без альтернативных ключей.

## Триггер / repro
Клиент, отправляющий sender-документ под ключом `document`/`attachment` (как разрешено для receiver), получает 422; для receiver тот же ключ работает.

## Корневая причина (гипотеза)
Sender-request и контроллерная ветка не выровнены с receiver-request после введения `getFiles()`/alternate-keys.

## Радиус поражения
Только контракт API на sender-upload; данные не портятся.

## Направление фикса (1-2 строки, НЕ реализовано)
Привести `UploadSenderDocumentRequest` к тому же набору ключей + `getFiles()`, либо явно задокументировать, что sender принимает только `file`/`files`.
