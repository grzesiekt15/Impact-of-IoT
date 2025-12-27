# Scenariusze testów OPEN/AUTH (HTTP, MQTT, CoAP)
# Uwaga: `run_experiments.sh` używa `tshark` (wymaga sudo do zapisu pcap). Odpalaj go z sudo albo zapewnij uprawnienia do capture.

Przygotuj plik `configs/.env.auth` z `AUTH_MODE=auth`, `API_TOKEN=supersekret123`, `MQTT_USER=mqtt_user`, `MQTT_PASS=mqtt_password`.

## Wspólne czyszczenie
```
./scripts/stop_clients.sh || true
docker compose down || true
```

## OPEN / HTTP
```
docker compose up -d --build
./scripts/start_clients.sh 3 http 1 open_http1 open
docker compose logs --tail 20 http-server   # oczekiwane: tylko info o starcie, brak 401
docker logs client_http_1 | head            # oczekiwane: HTTP LOOP START, status=200
```
Oczekiwania: w CSV `results/open_http1/metrics_open_http1_http_id*.csv` status=200, brak error; logi serwera bez 401, logi klienta bez ERR.

## OPEN / MQTT
```
docker compose up -d --build
./scripts/start_clients.sh 3 mqtt 1 open_mqtt1 open
docker compose logs --tail 20 mqtt-broker   # oczekiwane: brak “not authorised”
docker logs client_mqtt_1 | head            # oczekiwane: broker=mqtt-broker, RTT OK
```
Oczekiwania: CSV `results/open_mqtt1/metrics_open_mqtt1_mqtt_id*.csv` z status=OK/RTT, brak error; logi brokera bez “not authorised”.

## OPEN / CoAP
```
docker compose up -d --build
./scripts/start_clients.sh 3 coap 1 open_coap1 open
docker compose logs --tail 20 coap-server   # oczekiwane: Received CoAP POST..., brak Unauthorized
docker logs client_coap_1 | head            # oczekiwane: RTT OK
```
Oczekiwania: CSV `results/open_coap1/metrics_open_coap1_coap_id*.csv` status=OK, brak error; logi serwera bez “Unauthorized”.

## AUTH / HTTP
```
./scripts/stop_clients.sh || true
docker compose down || true
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d --build
./scripts/start_clients.sh 3 http 1 auth_http1 auth
docker compose -f docker-compose.yml -f docker-compose.auth.yml logs --tail 20 http-server   # oczekiwane: brak 401
docker logs client_http_1 | head                                                            # oczekiwane: Authorization wysyłany, status=200
```
Oczekiwania: CSV `results/auth_http1/metrics_auth_http1_http_id*.csv` status=200, brak error; serwer bez 401; klient pokazuje nagłówek Authorization i brak ERR.

## AUTH / MQTT
```
./scripts/stop_clients.sh || true
docker compose down || true
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d --build
./scripts/start_clients.sh 3 mqtt 1 auth_mqtt1 auth
docker compose -f docker-compose.yml -f docker-compose.auth.yml logs --tail 20 mqtt-broker   # oczekiwane: brak “not authorised”
docker logs client_mqtt_1 | head                                                            # oczekiwane: AUTH_MODE=auth, RTT OK
```
Oczekiwania: CSV `results/auth_mqtt1/metrics_auth_mqtt1_mqtt_id*.csv` status=OK/RTT, brak error; broker logi bez “not authorised”.

## AUTH / CoAP
```
./scripts/stop_clients.sh || true
docker compose down || true
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d --build
./scripts/start_clients.sh 3 coap 1 auth_coap1 auth
docker compose -f docker-compose.yml -f docker-compose.auth.yml logs --tail 20 coap-server   # oczekiwane: brak “Unauthorized CoAP (bad token)”
docker logs client_coap_1 | head                                                            # oczekiwane: RTT OK
```
Oczekiwania: CSV `results/auth_coap1/metrics_auth_coap1_coap_id*.csv` status=OK, brak error; serwer bez “Unauthorized”.

## Wyniki i oczekiwania
- CSV z RTT/status: `results/<RUN_ID>/metrics_<RUN_ID>_<proto>_id*.csv` (RUN_ID to 5. argument w `start_clients.sh`).
- OPEN: brak nagłówków/tokenów, brak „not authorised”; statusy OK/200, RTT stabilne.
- AUTH: HTTP 200 z nagłówkiem Authorization, MQTT bez „not authorised”, CoAP bez „Unauthorized CoAP (bad token)”; RTT podobne lub minimalnie wyższe.

## Zbieranie pcap do porównań
Użyj `scripts/run_experiments.sh N PROTO DURATION RUN_ID` po uruchomieniu właściwego stacka (open lub auth). Skrypt sam startuje klientów, zbiera pcap (`results_<RUN_ID>/<RUN_ID>_N${N}_${PROTO}.pcap`), logi RTT i sprząta.

Przykład OPEN (mqtt):
```
docker compose up -d --build
./scripts/run_experiments.sh 5 mqtt 15 open_mqtt_pcap
```

Przykład AUTH (mqtt):
```
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d --build
./scripts/run_experiments.sh 5 mqtt 15 auth_mqtt_pcap
```

Pełne 6 scenariuszy z `run_experiments.sh` (RTT + pcap):
- OPEN/HTTP:
```
docker compose up -d --build
./scripts/run_experiments.sh 5 http 15 open_http_pcap open
```
- Oczekiwania: CSV `results_open_http_pcap/` z status=200, brak error; pcap bez 401.
- OPEN/MQTT:
```
docker compose up -d --build
./scripts/run_experiments.sh 5 mqtt 15 open_mqtt_pcap open
```
- Oczekiwania: CSV `results_open_mqtt_pcap/` status=OK/RTT, brak error; pcap bez “not authorised”, CONNECT bez user/pass.
- OPEN/CoAP:
```
docker compose up -d --build
./scripts/run_experiments.sh 5 coap 15 open_coap_pcap open
```
- Oczekiwania: CSV `results_open_coap_pcap/` status=OK, brak error; pcap POST bez tokenu, brak CoAP Unauthorized.
- AUTH/HTTP:
```
docker compose down || true
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d --build
./scripts/run_experiments.sh 5 http 15 auth_http_pcap auth
```
- Oczekiwania: CSV `results_auth_http_pcap/` status=200, brak error; pcap z nagłówkiem Authorization, brak 401.
- AUTH/MQTT:
```
docker compose down || true
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d --build
./scripts/run_experiments.sh 5 mqtt 15 auth_mqtt_pcap auth
```
- Oczekiwania: CSV `results_auth_mqtt_pcap/` status=OK/RTT, brak error; pcap CONNECT z user/pass, brak “not authorised”.
- AUTH/CoAP:
```
docker compose down || true
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d --build
./scripts/run_experiments.sh 5 coap 15 auth_coap_pcap auth
```
- Oczekiwania: CSV `results_auth_coap_pcap/` status=OK, brak error; pcap z `?token=...`, brak CoAP Unauthorized.

Oczekiwane różnice w pcap:
- HTTP: w auth każdy POST ma nagłówek Authorization (większa ramka/segment).
- MQTT: w auth pakiet CONNECT większy (username/password); reszta ruchu podobna.
- CoAP: w auth każdy POST z `?token=...` w URI (dłuższy datagram).
- Przy złej konfiguracji auth zobaczysz 401 (HTTP), CONNACK 0x05/rozłączenia (MQTT) lub CoAP 4.01 Unauthorized.

Typowe różnice OPEN vs AUTH w pcap (co sprawdzać):
- HTTP: obecność/rozmiar nagłówka Authorization w AUTH; większy request; ewentualne 401 przy złej konfiguracji.
- MQTT: w AUTH pierwszy pakiet CONNECT zawiera username/password (większa długość i flagi); w OPEN CONNECT krótszy/anonimowy. Reszta PUBLISH/ACK podobna.
- CoAP: w AUTH URI zawiera `?token=...` w każdej wiadomości, więc dłuższe datagramy; w OPEN brak tokenu. Błędny token daje odpowiedź 4.01 Unauthorized.

Jeśli `tshark` zgłasza "Permission denied" przy zapisie pcap:
- Upewnij się, że katalog `results_<RUN_ID>` jest zapisywalny (`ls -ld results_<RUN_ID>`).
- Uruchom `run_experiments.sh` z uprawnieniami do capture (`sudo ./scripts/run_experiments.sh ...`) albo skonfiguruj `dumpcap` z capabilities (np. `sudo setcap 'CAP_NET_RAW+eip CAP_NET_ADMIN+eip' $(which dumpcap)` i wtedy uruchamiaj bez sudo).
