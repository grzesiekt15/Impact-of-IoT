#!/bin/bash
# Usage: sudo ./run_experiment.sh N PROTO DURATION_SEC out_prefix
N=${1:-10}
PROTO=${2:-mqtt}
DUR=${3:-180}
OUT=${4:-exp}
MODE=${5:-open}
KEEP_CLIENTS=${KEEP_CLIENTS:-0}
LOGDIR=./results_${OUT}
OWNER=${SUDO_USER:-$USER}
OWNER_GROUP=$(id -gn "$OWNER" 2>/dev/null || echo "$OWNER")
mkdir -p $LOGDIR

# clear old clients
./scripts/stop_clients.sh

# start capture (tshark) on all interfaces into pcap BEFORE klientów, żeby złapać handshake
PCAP_FILE=$LOGDIR/${OUT}_N${N}_${PROTO}.pcap
sudo timeout $DUR tshark -i any -w $PCAP_FILE &
TSHARK_PID=$!

# chwilowy bufor, żeby sniffing ruszył przed startem klientów
sleep 3

# start new clients (handshake trafi do pcap)
./scripts/start_clients.sh $N $PROTO 1 "$OUT" "$MODE"

# zapisz mapowanie kontener -> IP, aby móc powiązać z pcap
docker inspect -f '{{.Name}} {{.NetworkSettings.Networks.impact-of-iot_default.IPAddress}}' $(docker ps -q --filter "name=client_") 2>/dev/null > "$LOGDIR/clients_ips.txt" || true

# collect docker stats
docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" > $LOGDIR/docker_stats_N${N}_${PROTO}.csv

# collect system snapshot during test (simple)
top -b -n1 > $LOGDIR/top_N${N}_${PROTO}.txt
free -h > $LOGDIR/mem_N${N}_${PROTO}.txt

# wait until capture finishes
wait $TSHARK_PID || true

# === NOWE: zbierz RTT z logów klientów ZANIM je usuniesz ===
RTT_FILE=$LOGDIR/${OUT}_N${N}_${PROTO}_rtt.log
: > "$RTT_FILE"
echo "Collecting RTT metrics into $RTT_FILE"

for i in $(seq 1 $N); do
  cname="client_${PROTO}_${i}"
  echo "  -> from container $cname"
  docker logs "$cname" 2>/dev/null >> "$RTT_FILE"
done

# stop clients (chyba że KEEP_CLIENTS=1)
if [ "$KEEP_CLIENTS" != "1" ]; then
  ./scripts/stop_clients.sh
else
  echo "KEEP_CLIENTS=1 -> kontenery klienckie pozostawione uruchomione"
fi

# ensure current user can read the artifacts (pcaps owned by root otherwise)
chown -R "$OWNER":"$OWNER_GROUP" "$LOGDIR"

echo "Experiment finished. Files in $LOGDIR"
