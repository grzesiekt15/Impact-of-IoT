#!/usr/bin/env bash
set -euo pipefail

# Domyślne parametry serii
DUR="${DUR:-20}"                 # stały czas testu (polecam 20 albo 30)
REPS="${REPS:-2}"                # powtórzenia
NS="${NS:-10 50 100 200}"        # load scaling
SERIES="${SERIES:-series_$(date +%F_%H%M%S)}"
USE_SUDO="${USE_SUDO:-auto}"     # auto|always|never – jak wołać run_experiments
CLEAN_SOURCES="${CLEAN_SOURCES:-1}" # po rsync usuń oryginalne katalogi results_* / results/<id>
SKIP_COMPOSE_UP="${SKIP_COMPOSE_UP:-0}"    # 1 = nie rób docker compose up (użytkownik podnosi stack ręcznie)
SKIP_COMPOSE_DOWN="${SKIP_COMPOSE_DOWN:-0}" # 1 = nie rób docker compose down w hard_clean

PROTOS=("http" "mqtt" "coap")

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTROOT="$PROJECT_DIR/results/$SERIES"

# Compose dla OPEN i AUTH (AUTH wymaga docker-compose.auth.yml – jak w SCENARIOS.md)
OPEN_COMPOSE=(docker compose -f docker-compose.yml)
AUTH_COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.auth.yml)

CAN_SUDO=0
if command -v sudo >/dev/null 2>&1; then
  if sudo -n true >/dev/null 2>&1; then
    CAN_SUDO=1
  else
    echo "[INFO] sudo nie działa bez hasła / blokada NNP – domyślnie odpalę bez sudo"
  fi
else
  echo "[INFO] brak sudo w PATH – domyślnie odpalę bez sudo"
fi

echo "SERIES=$SERIES | DUR=$DUR | REPS=$REPS | NS=$NS"
echo "OUTROOT=$OUTROOT"
echo "USE_SUDO=$USE_SUDO (CAN_SUDO=$CAN_SUDO) | SKIP_COMPOSE_UP=$SKIP_COMPOSE_UP SKIP_COMPOSE_DOWN=$SKIP_COMPOSE_DOWN"
mkdir -p "$OUTROOT"

hard_clean() {
  echo "[CLEAN] stop clients + down -v"
  cd "$PROJECT_DIR"
  DOCKER_BIN="docker" ./scripts/stop_clients.sh >/dev/null 2>&1 || true
  if [[ "$SKIP_COMPOSE_DOWN" != "1" ]]; then
    docker compose down --remove-orphans -v >/dev/null 2>&1 || true
  else
    echo "[INFO] SKIP_COMPOSE_DOWN=1 -> pomijam docker compose down"
  fi
  sudo pkill -f tshark >/dev/null 2>&1 || true
}

run_one() {
  local mode="$1" proto="$2" n="$3" rep="$4"
  local run_id="${mode}_${proto}_N${n}_rep${rep}"
  local src_dir1="$PROJECT_DIR/results_${run_id}"      # tak zapisuje run_experiments.sh
  local src_dir2="$PROJECT_DIR/results/$run_id"        # czasem tak bywa w innych wersjach
  local dst_dir="$OUTROOT/$proto/$mode/N${n}/rep${rep}"
  local status=0

  mkdir -p "$dst_dir"

  echo "=== RUN: $run_id ==="

  # ważne: jeśli u Ciebie run_experiments wymaga sudo dla capture, zostaw sudo
  local run_log="$dst_dir/run_experiments.log"
  case "$USE_SUDO" in
    always)
      if ! sudo ./scripts/run_experiments.sh "$n" "$proto" "$DUR" "$run_id" "$mode" >"$run_log" 2>&1; then
        status=$?
      fi
      ;;
    never)
      if ! ./scripts/run_experiments.sh "$n" "$proto" "$DUR" "$run_id" "$mode" >"$run_log" 2>&1; then
        status=$?
      fi
      ;;
    *)
      if [[ "$CAN_SUDO" -eq 1 ]]; then
        if ! sudo ./scripts/run_experiments.sh "$n" "$proto" "$DUR" "$run_id" "$mode" >"$run_log" 2>&1; then
          status=$?
        fi
      else
        if ! ./scripts/run_experiments.sh "$n" "$proto" "$DUR" "$run_id" "$mode" >"$run_log" 2>&1; then
          status=$?
        fi
      fi
      ;;
  esac

  if [[ "$status" -ne 0 ]]; then
    echo "[WARN] run_experiments exit=$status dla $run_id"
  fi

  # Zbierz wyniki do ustandaryzowanej struktury serii
  if [[ -d "$src_dir1" ]]; then
    rsync -a "$src_dir1/" "$dst_dir/"
  elif [[ -d "$src_dir2" ]]; then
    rsync -a "$src_dir2/" "$dst_dir/"
  else
    echo "[WARN] nie znaleziono folderu wyników dla $run_id"
  fi
  if [[ "$CLEAN_SOURCES" == "1" ]]; then
    rm -rf "$src_dir1" "$src_dir2" 2>/dev/null || true
  fi

  # Dodatkowo dorzuć logi stacka (super przy debugowaniu)
  docker compose logs --no-color > "$dst_dir/docker_logs.txt" 2>/dev/null || true

  # Szybki sanity: czy jest jakiś pcap?
  if ! ls "$dst_dir"/*.pcap "$dst_dir"/*.pcapng >/dev/null 2>&1; then
    echo "[WARN] brak PCAP w $dst_dir"
  fi

  echo
}

mode_block() {
  local mode="$1"
  echo "############################"
  echo "# MODE: $mode"
  echo "############################"

  for n in $NS; do
    for rep in $(seq 1 "$REPS"); do
      for proto in "${PROTOS[@]}"; do
        run_one "$mode" "$proto" "$n" "$rep"
      done
    done
  done

  hard_clean
}

if [[ "${RUN_MODES:-open auth}" =~ open ]]; then
  cd "$PROJECT_DIR"
  hard_clean
  if [[ "$SKIP_COMPOSE_UP" != "1" ]]; then
    "${OPEN_COMPOSE[@]}" up -d --build
  else
    echo "[INFO] SKIP_COMPOSE_UP=1 -> zakładam, że stack OPEN już działa"
  fi
  mode_block "open"
fi

if [[ "${RUN_MODES:-open auth}" =~ auth ]]; then
  cd "$PROJECT_DIR"
  hard_clean
  if [[ "$SKIP_COMPOSE_UP" != "1" ]]; then
    "${AUTH_COMPOSE[@]}" up -d --build
  else
    echo "[INFO] SKIP_COMPOSE_UP=1 -> zakładam, że stack AUTH już działa"
  fi
  mode_block "auth"
fi

echo "DONE. Wyniki: $OUTROOT"
