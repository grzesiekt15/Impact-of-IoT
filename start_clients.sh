#!/bin/bash
# Usage: ./start_clients.sh N PROTO FREQ
N=${1:-10}
PROTO=${2:-mqtt}
FREQ=${3:-1}
COAP_HOST=${COAP_HOST:-localhost}
COAP_PORT=${COAP_PORT:-5683}
COAP_RESOURCE=${COAP_RESOURCE:-sensors}

echo "Starting $N clients proto=$PROTO freq=$FREQ"

# ensure old clients are removed
./stop_clients.sh

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
    iot-client:latest
done
