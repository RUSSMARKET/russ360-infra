# Rusaifin edge canary

Конфигурации этого каталога описывают canary-ingress
`edge2.rusaifin.ru` (`82.146.45.198`) перед production origin
`82.146.57.149`.

## Назначение

Canary позволяет проверить пользовательский путь через другой публичный IPv4
и другую подсеть без переноса приложения, API или базы данных. Оба адреса всё
ещё находятся у FirstVDS/Timeweb, поэтому стабильная работа canary доказывает
проблему конкретного адреса/маршрута, а одновременный сбой обоих адресов —
проблему более широкого пути до сети провайдера.

## Состав

- `a1-rusaifin-canary.nginx.conf` — TLS reverse proxy и same-origin runtime
  URLs для API/OIDC; ранний canary-only `fetch`/XHR shim также перехватывает
  legacy API hostname, разрешённый до гидрации runtime config;
- `a1-rusaifin-canary.nftables.conf` — вход только на 22, 80 и 443;
- `a1-certbot-deploy-hook` — проверка конфигурации и reload nginx после
  продления сертификата;
- `a1-rusaifin-bootstrap.nginx.conf` — минимальная HTTP-конфигурация для
  первичного выпуска сертификата.

## Проверка

```sh
curl -fsSI https://edge2.rusaifin.ru/products/
curl -fsSI https://edge2.rusaifin.ru/ | grep -i '^x-rusaifin-canary-ingress:'
```

В браузере нужно проверить вход, продукты, фото и повторные холодные открытия
Safari.

## Откат

Canary не заменяет основной A-record и потому не требует DNS-отката. Для его
изоляции достаточно остановить nginx на `82.146.45.198` либо убрать только
A-record `edge2`; production `fintech.rusaifin.ru` останется без изменений.
Перед удалением OAuth callback URI необходимо убедиться, что canary больше не
используется.
