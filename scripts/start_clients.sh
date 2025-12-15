#!/bin/bash
# Usage: ./start_clients.sh N PROTO FREQ [RUN_ID]
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"


N=${1:-10}
PROTO=${2:-mqtt}
FREQ=${3:-1}

RUN_ID=${4:-$(date +%Y%m%d_%H%M%S)}
RESULTS_DIR="$(pwd)/results/$RUN_ID"

mkdir -p "$RESULTS_DIR"

COAP_HOST=${COAP_HOST:-127.0.0.1}
COAP_PORT=${COAP_PORT:-5683}
COAP_RESOURCE=${COAP_RESOURCE:-sensors}

echo "Starting $N clients proto=$PROTO freq=$FREQ"

# ensure old clients are removed
./scripts/stop_clients.sh

for i in $(seq 1 $N); do
  NAME="client_${PROTO}_${i}"
  echo "Starting $NAME"
  docker run -d \
    --name $NAME \
    --network host \
    -e ID=$i \
    -e FREQ=$FREQ \
    -e PROTO=$PROTO \
    -e COAP_HOST=$COAP_HOST \
    -e COAP_PORT=$COAP_PORT \
    -e COAP_RESOURCE=$COAP_RESOURCE \
    -v "$RESULTS_DIR:/results" \
    -e OUT_DIR=/results \
    -e RUN_ID="$RUN_ID" \
    iot-client:latest
done

echo "Results: $RESULTS_DIR"
