#!/bin/bash
# Stop and remove only IoT client containers
for c in $(docker ps -a --filter "name=client_" -q); do
    echo "Removing container $c"
    docker rm -f $c
done
