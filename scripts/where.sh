#!/usr/bin/env bash
#
# where.sh — снимок состояния всех репозиториев Russ360
#
#   scripts/where.sh           # таблица + per-repo граф
#   scripts/where.sh --table   # только таблица
#   scripts/where.sh --fetch   # сначала git fetch локально (для точного ahead/behind)
#   scripts/where.sh --no-ssh  # пропустить серверные проверки
#
# Сравнения:
#   ✓  локальный HEAD совпадает с dev/prod HEAD
#   ↑N локально на N коммитов впереди dev/prod
#   ↓N локально отстаёт на N
#   ⇄  расходящиеся истории (need rebase/merge)
#   ?  dev/prod sha не найден локально → запустить с --fetch
#
set -Euo pipefail

PROD_HOST="${PROD_HOST:-root@82.146.57.149}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# name|local_dir|dev_remote_path|prod_remote_path
REPOS=(
  "rusaiauth|rusaiauth|/home/Rusaiauth/web/dev.sso.rusaifin.ru/public_html|/home/Rusaiauth/web/sso.rusaifin.ru"
  "rusaicore|rusaicore|/home/Rusaicore/web/dev.server.rusaicore.ru/public_html|/home/Rusaicore/web/server.rusaicore.ru/public_html"
  "rusaifin|rusaifin|/home/fintech/web/dev.server.rusaifin.ru/public_html|/home/fintech/web/server.rusaifin.ru/public_html"
  "rusaisklad_back|rusaisklad_back|/home/Rusaisklad/web/dev.server.rusaisklad.ru/public_html|/home/Rusaisklad/web/server.rusaisklad.ru/public_html"
  "fintech|fintech|/home/fintech/web/dev.fintech.rusaifin.ru/public_html|/home/fintech/web/fintech.rusaifin.ru/public_html"
  "rusaisklad_front|rusaisklad_front|/home/Rusaisklad/web/dev.rusaisklad.ru/app|/home/Rusaisklad/web/rusaisklad.ru/app"
  "bibli|bibli|-|-"
)

MODE_TABLE=1
MODE_GRAPH=1
DO_FETCH=0
DO_SSH=1
for arg in "$@"; do
  case "$arg" in
    --table) MODE_GRAPH=0 ;;
    --graph) MODE_TABLE=0 ;;
    --fetch) DO_FETCH=1 ;;
    --no-ssh) DO_SSH=0 ;;
    -h|--help) sed -n '3,15p' "$0"; exit 0 ;;
  esac
done

if [[ -t 1 ]]; then
  C_RST=$'\033[0m'; C_DIM=$'\033[2m'; C_B=$'\033[1m'
  C_GRN=$'\033[32m'; C_RED=$'\033[31m'; C_YLW=$'\033[33m'
  C_CYN=$'\033[36m'; C_MAG=$'\033[35m'; C_BLU=$'\033[34m'
else
  C_RST=; C_DIM=; C_B=; C_GRN=; C_RED=; C_YLW=; C_CYN=; C_MAG=; C_BLU=
fi

ssh_cmd() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "${PROD_HOST}" "$@"
}

# Один ssh-вызов, который собирает все sha разом — экономит RTT.
collect_remote() {
  local script='set +e; '
  for entry in "${REPOS[@]}"; do
    IFS='|' read -r name _ devp prodp <<<"$entry"
    for env in dev prod; do
      local path
      [[ "$env" == "dev" ]] && path="$devp" || path="$prodp"
      [[ "$path" == "-" ]] && continue
      # экранируем пути на всякий случай
      script+="p=$(printf %q "$path"); n=$(printf %q "$name"); e=$(printf %q "$env"); "
      script+='if [ -d "$p/.git" ]; then '
      script+='br=$(git -C "$p" -c safe.directory="*" rev-parse --abbrev-ref HEAD 2>/dev/null); '
      script+='sha=$(git -C "$p" -c safe.directory="*" rev-parse --short HEAD 2>/dev/null); '
      script+='msg=$(git -C "$p" -c safe.directory="*" log -1 --format=%s 2>/dev/null | /usr/bin/tr "|" "/" | /usr/bin/cut -c1-72); '
      script+='echo "$n|$e|$br|$sha|$msg"; '
      script+='else echo "$n|$e|MISSING|-|-"; fi; '
    done
  done
  ssh_cmd "/bin/bash -c $(printf %q "$script")"
}

declare -A REMOTE_BR REMOTE_SHA REMOTE_MSG

if [[ $DO_SSH -eq 1 ]]; then
  while IFS='|' read -r name env br sha msg; do
    [[ -z "$name" ]] && continue
    REMOTE_BR["$name|$env"]="$br"
    REMOTE_SHA["$name|$env"]="$sha"
    REMOTE_MSG["$name|$env"]="$msg"
  done < <(collect_remote)
fi

# Сравнение локального HEAD и удалённого sha.
# Возвращает: ✓ / ↑N / ↓N / ⇄ / ?
cmp_local_remote() {
  local local_dir="$1" remote_sha="$2"
  [[ -z "$remote_sha" || "$remote_sha" == "-" || "$remote_sha" == "MISSING" ]] && { echo "—"; return; }
  if ! git -C "$local_dir" cat-file -e "${remote_sha}^{commit}" 2>/dev/null; then
    echo "${C_DIM}?${C_RST}"; return
  fi
  local local_sha
  local_sha=$(git -C "$local_dir" rev-parse HEAD)
  if [[ "$local_sha" == $(git -C "$local_dir" rev-parse "$remote_sha") ]]; then
    echo "${C_GRN}✓${C_RST}"; return
  fi
  local ahead behind
  ahead=$(git -C "$local_dir" rev-list --count "${remote_sha}..HEAD" 2>/dev/null || echo "?")
  behind=$(git -C "$local_dir" rev-list --count "HEAD..${remote_sha}" 2>/dev/null || echo "?")
  if [[ "$ahead" -gt 0 && "$behind" -gt 0 ]]; then
    echo "${C_MAG}⇄ ↑${ahead}/↓${behind}${C_RST}"
  elif [[ "$ahead" -gt 0 ]]; then
    echo "${C_YLW}↑${ahead}${C_RST}"
  else
    echo "${C_RED}↓${behind}${C_RST}"
  fi
}

print_table() {
  printf "${C_B}%-18s %-22s %-22s %-22s${C_RST}\n" "REPO" "LOCAL" "DEV" "PROD"
  printf "${C_DIM}%-18s %-22s %-22s %-22s${C_RST}\n" "----" "-----" "---" "----"
  for entry in "${REPOS[@]}"; do
    IFS='|' read -r name local_sub _ _ <<<"$entry"
    local ldir="${REPO_ROOT}/${local_sub}"
    if [[ ! -d "$ldir/.git" ]]; then
      printf "%-18s ${C_DIM}%-22s${C_RST}\n" "$name" "no local repo"
      continue
    fi
    local lbr lsha dirty=""
    lbr=$(git -C "$ldir" rev-parse --abbrev-ref HEAD 2>/dev/null)
    lsha=$(git -C "$ldir" rev-parse --short HEAD 2>/dev/null)
    [[ -n "$(git -C "$ldir" status --porcelain 2>/dev/null)" ]] && dirty="${C_RED}*${C_RST}"
    [[ $DO_FETCH -eq 1 ]] && git -C "$ldir" fetch --quiet --all 2>/dev/null || true

    local dev_br="${REMOTE_BR[$name|dev]:-—}" dev_sha="${REMOTE_SHA[$name|dev]:-—}"
    local prod_br="${REMOTE_BR[$name|prod]:-—}" prod_sha="${REMOTE_SHA[$name|prod]:-—}"
    local dev_cmp prod_cmp
    dev_cmp=$(cmp_local_remote "$ldir" "$dev_sha")
    prod_cmp=$(cmp_local_remote "$ldir" "$prod_sha")

    printf "%-18s ${C_CYN}%-8s${C_RST} %-9s%b   ${C_BLU}%-8s${C_RST} %-9s %b   ${C_BLU}%-8s${C_RST} %-9s %b\n" \
      "$name" "$lbr" "$lsha" "$dirty" \
      "$dev_br" "$dev_sha" "$dev_cmp" \
      "$prod_br" "$prod_sha" "$prod_cmp"
  done
  printf "\n${C_DIM}legend:  ${C_GRN}✓${C_DIM} same  ${C_YLW}↑N${C_DIM} local ahead  ${C_RED}↓N${C_DIM} local behind  ${C_MAG}⇄${C_DIM} diverged  ?${C_DIM} sha unknown locally (--fetch)  ${C_RED}*${C_DIM} dirty${C_RST}\n"
}

print_graph() {
  echo
  printf "${C_B}── per-repo flow ──${C_RST}\n"
  for entry in "${REPOS[@]}"; do
    IFS='|' read -r name local_sub _ _ <<<"$entry"
    local ldir="${REPO_ROOT}/${local_sub}"
    [[ ! -d "$ldir/.git" ]] && continue
    local lbr lsha lmsg
    lbr=$(git -C "$ldir" rev-parse --abbrev-ref HEAD)
    lsha=$(git -C "$ldir" rev-parse --short HEAD)
    lmsg=$(git -C "$ldir" log -1 --format='%s' | cut -c1-70)
    local dev_br="${REMOTE_BR[$name|dev]:-—}" dev_sha="${REMOTE_SHA[$name|dev]:-—}" dev_msg="${REMOTE_MSG[$name|dev]:--}"
    local prod_br="${REMOTE_BR[$name|prod]:-—}" prod_sha="${REMOTE_SHA[$name|prod]:-—}" prod_msg="${REMOTE_MSG[$name|prod]:--}"
    local dev_cmp prod_cmp
    dev_cmp=$(cmp_local_remote "$ldir" "$dev_sha")
    prod_cmp=$(cmp_local_remote "$ldir" "$prod_sha")
    echo
    printf "${C_B}%s${C_RST}\n" "$name"
    printf "  ${C_CYN}local${C_RST}  %-8s %-9s  %s\n" "$lbr" "$lsha" "$lmsg"
    printf "  ${C_BLU}dev${C_RST}    %-8s %-9s  %s   %b\n" "$dev_br" "$dev_sha" "$dev_msg" "$dev_cmp"
    printf "  ${C_BLU}prod${C_RST}   %-8s %-9s  %s   %b\n" "$prod_br" "$prod_sha" "$prod_msg" "$prod_cmp"
  done
}

# Bibli — npm-зависимость, sha зашит в package-lock.json каждого фронта.
# Показываем какие коммиты bibli фактически собраны на каждой среде.
print_bibli() {
  local local_bibli_sha
  local_bibli_sha=$(git -C "${REPO_ROOT}/bibli" rev-parse --short HEAD 2>/dev/null || echo "?")

  # local front-pin
  local fin_local skl_local
  fin_local=$(extract_bibli_sha "${REPO_ROOT}/fintech/package-lock.json")
  skl_local=$(extract_bibli_sha "${REPO_ROOT}/rusaisklad_front/package-lock.json")

  # remote front-pins (один ssh-вызов)
  if [[ $DO_SSH -eq 1 ]]; then
    local remote_out
    remote_out=$(ssh_cmd 'for p in \
      /home/fintech/web/dev.fintech.rusaifin.ru/public_html \
      /home/fintech/web/fintech.rusaifin.ru/public_html \
      /home/Rusaisklad/web/dev.rusaisklad.ru/app \
      /home/Rusaisklad/web/rusaisklad.ru/app ; do
      sha=$(jq -r "[.packages | to_entries[] | select(.key | endswith(\"bibli\"))] | first | .value | .resolved // \"-\"" "$p/package-lock.json" 2>/dev/null | sed -E "s|.*#||" | cut -c1-7)
      echo "$p|${sha:--}"
    done' 2>/dev/null)
    fin_dev=$(echo "$remote_out" | grep "dev.fintech.rusaifin.ru" | cut -d'|' -f2)
    fin_prod=$(echo "$remote_out" | grep "/web/fintech.rusaifin.ru" | cut -d'|' -f2)
    skl_dev=$(echo "$remote_out" | grep "dev.rusaisklad.ru" | cut -d'|' -f2)
    skl_prod=$(echo "$remote_out" | grep "/web/rusaisklad.ru" | cut -d'|' -f2)
  else
    fin_dev=skl_dev=fin_prod=skl_prod="—"
  fi

  echo
  printf "${C_B}── bibli pins ──${C_RST}  ${C_DIM}(sha из package-lock.json; локально HEAD=%s)${C_RST}\n" "$local_bibli_sha"
  printf "%-18s %-12s %-12s %-12s\n" "FRONT" "local-pin" "dev-pin" "prod-pin"
  printf "%-18s %-12s %-12s %-12s\n" "fintech" "${fin_local:-—}" "${fin_dev:-—}" "${fin_prod:-—}"
  printf "%-18s %-12s %-12s %-12s\n" "rusaisklad_front" "${skl_local:-—}" "${skl_dev:-—}" "${skl_prod:-—}"
}

extract_bibli_sha() {
  local lock="$1"
  [[ ! -f "$lock" ]] && { echo "—"; return; }
  local sha
  sha=$(jq -r '[.packages | to_entries[] | select(.key | endswith("bibli"))] | first | .value | .resolved // "-"' "$lock" 2>/dev/null | sed -E 's|.*#||' | cut -c1-7)
  echo "${sha:--}"
}

[[ $MODE_TABLE -eq 1 ]] && print_table
[[ $MODE_GRAPH -eq 1 ]] && print_graph
[[ $MODE_TABLE -eq 1 || $MODE_GRAPH -eq 1 ]] && print_bibli
