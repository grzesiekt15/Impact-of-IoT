#!/bin/bash
# Usage: ./start_clients.sh N PROTO FREQ [RUN_ID]
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${5:-open}"   # domyślnie open
ENV_FILE="configs/.env.${MODE}"

N=${1:-10}
PROTO=${2:-mqtt}
FREQ=${3:-1}

RUN_ID=${4:-$(date +%Y%m%d_%H%M%S)}
RESULTS_DIR_BASE="${RESULTS_DIR_BASE:-$(pwd)/results}"
RESULTS_DIR="$RESULTS_DIR_BASE/$RUN_ID"
DOCKER_BIN=${DOCKER_BIN:-docker}
START_FILE_TIMEOUT=${START_FILE_TIMEOUT:-300}
READY_FILE_PREFIX="${READY_FILE_PREFIX:-.ready_${RUN_ID}_}"
MAX_SAMPLES="${MAX_SAMPLES:-0}"

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
  echo "MODE=$MODE ENV_FILE=$ENV_FILE"
  "$DOCKER_BIN" run -d \
    --name $NAME \
    --network impact-of-iot_default \
    --env-file "$ENV_FILE" \
    -e ID=$i \
    -e FREQ=$FREQ \
    -e PROTO=$PROTO \
    -e AUTH_MODE="$MODE" \
    -e HTTP_URL=http://http-server:5000/post \
    -e BROKER=mqtt-broker \
    -e COAP_HOST=coap-server \
    -e COAP_PORT=$COAP_PORT \
    -e COAP_RESOURCE=$COAP_RESOURCE \
    -v "$RESULTS_DIR:/results" \
    -e OUT_DIR=/results \
    -e RUN_ID="$RUN_ID" \
    -e START_FILE="/results/.start_${RUN_ID}" \
    -e START_FILE_TIMEOUT="$START_FILE_TIMEOUT" \
    -e STOP_FILE="/results/.stop_${RUN_ID}" \
    -e MAX_SAMPLES="$MAX_SAMPLES" \
    -e READY_FILE="/results/${READY_FILE_PREFIX}${i}" \
    iot-client:latest
done

echo "Results: $RESULTS_DIR"
