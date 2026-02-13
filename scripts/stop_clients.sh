#!/bin/bash
# Stop and remove only IoT client containers
DOCKER_BIN=${DOCKER_BIN:-docker}
for c in $($DOCKER_BIN ps -a --filter "name=client_" -q); do
    echo "Removing container $c"
    $DOCKER_BIN rm -f $c
done
