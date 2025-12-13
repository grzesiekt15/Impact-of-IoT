#!/bin/bash
# Usage: sudo ./run_experiment.sh N PROTO DURATION_SEC out_prefix
N=${1:-10}
PROTO=${2:-mqtt}
DUR=${3:-180}
OUT=${4:-exp}
LOGDIR=./results_${OUT}
OWNER=${SUDO_USER:-$USER}
OWNER_GROUP=$(id -gn "$OWNER" 2>/dev/null || echo "$OWNER")
mkdir -p $LOGDIR

# clear old clients and start new
./stop_clients.sh
./start_clients.sh $N $PROTO 1

# start capture (tshark) on all interfaces into pcap
PCAP_FILE=$LOGDIR/${OUT}_N${N}_${PROTO}.pcap
sudo timeout $DUR tshark -i any -w $PCAP_FILE &
TSHARK_PID=$!

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

# stop clients
./stop_clients.sh

# ensure current user can read the artifacts (pcaps owned by root otherwise)
chown -R "$OWNER":"$OWNER_GROUP" "$LOGDIR"

echo "Experiment finished. Files in $LOGDIR"
