#!/bin/bash
# Usage: sudo ./run_experiment.sh N PROTO DURATION_SEC out_prefix
N=${1:-10}
PROTO=${2:-mqtt}
DUR=${3:-180}
OUT=${4:-exp}
MODE=${5:-open}
KEEP_CLIENTS=${KEEP_CLIENTS:-0}
USE_SUDO_CAPTURE=${USE_SUDO_CAPTURE:-auto} # auto|always|never
STARTUP_PAD=${STARTUP_PAD:-0}   # dodatkowe sekundy dla capture na rozruch wielu klientów
CAPTURE_DUR=${CAPTURE_DUR:-$((DUR + STARTUP_PAD))}
CAPTURE_AFTER_START=${CAPTURE_AFTER_START:-0} # 1 = odpal capture dopiero po starcie klientów
STARTUP_WAIT_MAX=${STARTUP_WAIT_MAX:-60}      # ile maks czekać na N klientów (sek)
STARTUP_WAIT_INTERVAL=${STARTUP_WAIT_INTERVAL:-2}
STARTUP_READY_SLEEP=${STARTUP_READY_SLEEP:-0} # dodatkowy sleep po wykryciu N klientów (sek)
READY_WAIT_MAX=${READY_WAIT_MAX:-120}         # ile maks czekać na pliki READY (sek); 0 = bez limitu
READY_WAIT_INTERVAL=${READY_WAIT_INTERVAL:-2}
CAPTURE_IF=${CAPTURE_IF:-auto}   # interfejs do sniffingu (auto/any/br-*)
CAPTURE_FILTER=${CAPTURE_FILTER:-} # opcjonalny filtr BPF dla tshark (-f), np. "tcp port 5000"
STOP_WAIT=${STOP_WAIT:-5}       # ile czekać po STOP_FILE zanim zacznie zbieranie logów
LOGDIR=./results_${OUT}
RUN_DIR="$LOGDIR/$OUT"
CAPTURE_LOG=$LOGDIR/tshark.log
OWNER=${SUDO_USER:-$USER}
OWNER_GROUP=$(id -gn "$OWNER" 2>/dev/null || echo "$OWNER")
mkdir -p "$LOGDIR"
mkdir -p "$RUN_DIR"
DOCKER_BIN="docker"
START_FILE="$RUN_DIR/.start_${OUT}"
READY_PREFIX="$RUN_DIR/.ready_${OUT}_"
STOP_FILE="$RUN_DIR/.stop_${OUT}"

# configure sudo usage (for capture/chown)
SUDO_CMD=()
case "$USE_SUDO_CAPTURE" in
  always)
    SUDO_CMD=(sudo)
    ;;
  never)
    SUDO_CMD=()
    ;;
  *)
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
      SUDO_CMD=(sudo)
    else
      echo "[INFO] sudo unavailable for capture; running without sudo"
      SUDO_CMD=()
    fi
    ;;
esac

sudo_wrap() {
  if [ "${#SUDO_CMD[@]}" -gt 0 ]; then
    "${SUDO_CMD[@]}" "$@"
  else
    "$@"
  fi
}

if [ "${#SUDO_CMD[@]}" -gt 0 ]; then
  DOCKER_BIN="sudo docker"
fi

# verify docker access early to avoid silent failures
if ! sudo_wrap docker ps >/dev/null 2>&1; then
  echo "[ERROR] docker not reachable (socket permission?). Dodaj użytkownika do grupy docker albo ustaw USE_SUDO/USE_SUDO_CAPTURE=always."
  exit 1
fi

# auto-detect Docker bridge for capture if requested
if [ -z "$CAPTURE_IF" ] || [ "$CAPTURE_IF" = "auto" ]; then
  NET_ID=$(sudo_wrap docker network inspect -f '{{.Id}}' impact-of-iot_default 2>/dev/null | head -n1)
  if [ -n "$NET_ID" ]; then
    BR_IF="br-${NET_ID:0:12}"
    if command -v rg >/dev/null 2>&1; then
      if sudo_wrap tshark -D 2>/dev/null | rg -q "\\b${BR_IF}\\b"; then
        CAPTURE_IF="$BR_IF"
      fi
    else
      if sudo_wrap tshark -D 2>/dev/null | grep -q "\\b${BR_IF}\\b"; then
        CAPTURE_IF="$BR_IF"
      fi
    fi
  fi
  if [ -z "$CAPTURE_IF" ] || [ "$CAPTURE_IF" = "auto" ]; then
    CAPTURE_IF="any"
  fi
  echo "[INFO] CAPTURE_IF auto-selected: $CAPTURE_IF"
fi

# clear old clients
DOCKER_BIN="docker"

# clear old clients
DOCKER_BIN="$DOCKER_BIN" ./scripts/stop_clients.sh
rm -f "$START_FILE" || true
rm -f "$READY_PREFIX"* 2>/dev/null || true
rm -f "$STOP_FILE" || true

PCAP_FILE=$LOGDIR/${OUT}_N${N}_${PROTO}.pcap
PCAP_TMP=/tmp/${OUT}_N${N}_${PROTO}.pcap

start_capture() {
  sudo_wrap rm -f "$PCAP_TMP" || true
  echo "[INFO] tshark -i $CAPTURE_IF -w $PCAP_TMP (dur=${CAPTURE_DUR}s)" >"$CAPTURE_LOG"
  if [ -n "$CAPTURE_FILTER" ]; then
    echo "[INFO] CAPTURE_FILTER=$CAPTURE_FILTER" >>"$CAPTURE_LOG"
    sudo_wrap timeout "$CAPTURE_DUR" tshark -i "$CAPTURE_IF" -f "$CAPTURE_FILTER" -w "$PCAP_TMP" >>"$CAPTURE_LOG" 2>&1 &
  else
    sudo_wrap timeout "$CAPTURE_DUR" tshark -i "$CAPTURE_IF" -w "$PCAP_TMP" >>"$CAPTURE_LOG" 2>&1 &
  fi
  TSHARK_PID=$!
}

if [ "$CAPTURE_AFTER_START" = "1" ]; then
  echo "[INFO] CAPTURE_AFTER_START=1 -> najpierw start klientów, potem capture"
  RESULTS_DIR_BASE="$LOGDIR" DOCKER_BIN="$DOCKER_BIN" READY_FILE_PREFIX="$(basename "$READY_PREFIX")" ./scripts/start_clients.sh $N $PROTO 1 "$OUT" "$MODE"
  # poczekaj na wszystkie kontenery klienta
  waited=0
  while true; do
    running=$($DOCKER_BIN ps -q --filter "name=client_" | wc -l)
    if [ "$running" -ge "$N" ]; then
      break
    fi
    if [ "$waited" -ge "$STARTUP_WAIT_MAX" ]; then
      echo "[WARN] nie osiągnięto $N klientów w czasie $STARTUP_WAIT_MAX s (running=$running/$N)"
      break
    fi
    sleep "$STARTUP_WAIT_INTERVAL"
    waited=$((waited + STARTUP_WAIT_INTERVAL))
  done
  # poczekaj aż wszyscy klienci zapiszą READY_FILE
  waited_ready=0
  while true; do
    ready_count=$(ls -1 "$READY_PREFIX"* 2>/dev/null | wc -l)
    if [ "$ready_count" -ge "$N" ]; then
      break
    fi
    if [ "$READY_WAIT_MAX" -gt 0 ] && [ "$waited_ready" -ge "$READY_WAIT_MAX" ]; then
      echo "[WARN] READY files not complete (ready=$ready_count/$N) after ${READY_WAIT_MAX}s"
      break
    fi
    sleep "$READY_WAIT_INTERVAL"
    waited_ready=$((waited_ready + READY_WAIT_INTERVAL))
  done
  if [ "$STARTUP_READY_SLEEP" -gt 0 ]; then
    echo "[INFO] STARTUP_READY_SLEEP=$STARTUP_READY_SLEEP -> czekam po starcie klientów"
    sleep "$STARTUP_READY_SLEEP"
  fi
  start_capture
  # odblokuj ruch klientów po starcie capture
  date +%s > "$START_FILE"
else
  # domyślnie: capture przed klientami, łapie handshake
  start_capture
  sleep 3
  RESULTS_DIR_BASE="$LOGDIR" DOCKER_BIN="$DOCKER_BIN" READY_FILE_PREFIX="$(basename "$READY_PREFIX")" ./scripts/start_clients.sh $N $PROTO 1 "$OUT" "$MODE"
  date +%s > "$START_FILE"
fi

# zapisz mapowanie kontener -> IP, aby móc powiązać z pcap
CLIENT_IDS=$($DOCKER_BIN ps -q -a --filter "name=client_")
if [ -n "$CLIENT_IDS" ]; then
  if ! $DOCKER_BIN inspect -f '{{.Name}} {{.NetworkSettings.Networks.impact-of-iot_default.IPAddress}}' $CLIENT_IDS 2>/dev/null > "$LOGDIR/clients_ips.txt"; then
    echo "[WARN] docker inspect failed (permissions?). clients_ips.txt left empty" | tee -a "$CAPTURE_LOG" >/dev/null
    : > "$LOGDIR/clients_ips.txt"
  fi
else
  echo "[WARN] no client containers found -> clients_ips.txt will be empty" | tee -a "$CAPTURE_LOG" >/dev/null
  : > "$LOGDIR/clients_ips.txt"
fi

# collect docker stats
$DOCKER_BIN stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" > $LOGDIR/docker_stats_N${N}_${PROTO}.csv

# collect system snapshot during test (simple)
top -b -n1 > $LOGDIR/top_N${N}_${PROTO}.txt
free -h > $LOGDIR/mem_N${N}_${PROTO}.txt

# wait until capture finishes
wait $TSHARK_PID || true

# stop clients at the same moment (file-based barrier)
date +%s > "$STOP_FILE"
if [ "$STOP_WAIT" -gt 0 ]; then
  sleep "$STOP_WAIT"
fi

# przenieś PCAP do katalogu wyników
sudo_wrap mkdir -p "$LOGDIR"
if sudo_wrap mv -f "$PCAP_TMP" "$PCAP_FILE"; then
  :
else
  echo "[WARN] pcap move failed (capture may have failed)"
fi
if [ ! -s "$PCAP_FILE" ]; then
  echo "[WARN] pcap file missing or empty: $PCAP_FILE" | tee -a "$CAPTURE_LOG"
fi

# === NOWE: zbierz RTT z logów klientów ZANIM je usuniesz ===
RTT_FILE=$LOGDIR/${OUT}_N${N}_${PROTO}_rtt.log
: > "$RTT_FILE"
echo "Collecting RTT metrics into $RTT_FILE"

for i in $(seq 1 $N); do
  cname="client_${PROTO}_${i}"
  echo "  -> from container $cname"
  $DOCKER_BIN logs "$cname" 2>/dev/null >> "$RTT_FILE"
done

# stop clients (chyba że KEEP_CLIENTS=1)
if [ "$KEEP_CLIENTS" != "1" ]; then
  ./scripts/stop_clients.sh
else
  echo "KEEP_CLIENTS=1 -> kontenery klienckie pozostawione uruchomione"
fi

# ensure current user can read the artifacts (pcaps owned by root otherwise)
sudo_wrap chown -R "$OWNER":"$OWNER_GROUP" "$LOGDIR" || chown -R "$OWNER":"$OWNER_GROUP" "$LOGDIR" || true
sudo_wrap chmod -R u+rwX,go+rX "$LOGDIR" || chmod -R u+rwX,go+rX "$LOGDIR" || true

echo "Experiment finished. Files in $LOGDIR"
