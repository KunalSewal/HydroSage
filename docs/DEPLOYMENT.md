# Deploying on the four lab containers

The final deployment runs on four student containers on one host,
`10.1.75.53`. Each is capped at **512 MB**, is reached by SSH on its own
port, and publishes internal ports 3000 and 4000:

| SSH port | Role | Internal port | Public URL |
|---|---|---|---|
| 2265 | Phase 1 API (unchanged; can join the pool later) | 3000 | `http://10.1.75.53:3265` |
| 2266 | **Gateway**: website + load balancer | 3000 | **`http://10.1.75.53:3266`** ← the frontend URL |
| 2267 | Analysis API instance | 3000 | `http://10.1.75.53:3267` |
| 2268 | Analysis API instance | 3000 | `http://10.1.75.53:3268` |

Why this shape (docs/DECISIONS.md D-015): one analysis peaks at 305–500 MB,
so each 512 MB container can run exactly one at a time. The Phase 1 API on
2265 already uses that budget, so the gateway gets its own container. It
serves the website and the API from one origin (no CORS), sends each
analysis to a free instance (never two at once on one instance), queues a
bounded number of extras, and answers 503 with `Retry-After` beyond that
instead of letting a container be killed.

There is no database, Redis or MinIO on these machines. Clicking the map
analyzes a ~2.2 km square around the point, elevation downloads are cached
on each instance's disk, and results are cached in memory.

## Prerequisites (each machine)

Python 3.12 and git. Check with `python3 --version`. The repository is
cloned at `~/HydroSage` below; adjust paths if yours differs.

## 1. API instances: 2267 and 2268

On each of the two machines:

```bash
cd ~ && (test -d HydroSage || git clone https://github.com/KunalSewal/HydroSage.git)
cd ~/HydroSage && git checkout main && git pull
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp -n .env.example .env
```

Edit `backend/.env` and set `OPENTOPOGRAPHY_API_KEY=<your key>` (the same key
as local development). Then start it in tmux so it survives logout:

```bash
cd ~/HydroSage
tmux new-session -d -s api 'deploy/run_api.sh 2>&1 | tee -a ~/hydrosage-api.log'
sleep 20 && curl -s localhost:3000/health
```

Expected: `{"status":"ok","in_flight":0,"waiting":0}`. The first start
takes ~15–20 s (the geospatial libraries are large).

## 2. Gateway: 2266

```bash
cd ~ && (test -d HydroSage || git clone https://github.com/KunalSewal/HydroSage.git)
cd ~/HydroSage && git checkout main && git pull
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Get the built website. CI builds it on every push to `main` and publishes it
to the `frontend-dist` branch; the machines don't need Node:

```bash
cd ~ && (test -d hydrosage-web || git clone --branch frontend-dist --single-branch https://github.com/KunalSewal/HydroSage.git hydrosage-web)
git -C ~/hydrosage-web pull
```

Check that this container can reach the two API instances:

```bash
curl -s -m 5 http://10.1.75.53:3267/health; echo
curl -s -m 5 http://10.1.75.53:3268/health; echo
```

If both print `{"status":"ok",...}`, start the gateway:

```bash
cd ~/HydroSage
tmux new-session -d -s gateway 'GATEWAY_BACKENDS=http://10.1.75.53:3267,http://10.1.75.53:3268 deploy/run_gateway.sh 2>&1 | tee -a ~/hydrosage-gateway.log'
sleep 3 && curl -s localhost:3000/gateway/status; echo
```

If the public addresses don't answer from inside a container, use each API
container's internal address instead: run `hostname -I` on 2267 and 2268
and use `http://<that-ip>:3000` in `GATEWAY_BACKENDS`.

## 3. Check from outside

Open `http://10.1.75.53:3266` in a browser, draw an area, and wait for the
result (~15–30 s for a new area; a few seconds when repeated). The gateway's
view of the fleet is at `http://10.1.75.53:3266/gateway/status`.

## Updating after a new push

```bash
# API machines (2267, 2268)
cd ~/HydroSage && git pull && (cd backend && source .venv/bin/activate && pip install -e . -q)
tmux kill-session -t api; tmux new-session -d -s api 'deploy/run_api.sh 2>&1 | tee -a ~/hydrosage-api.log'

# Gateway machine (2266)
cd ~/HydroSage && git pull && git -C ~/hydrosage-web pull
tmux kill-session -t gateway; tmux new-session -d -s gateway 'GATEWAY_BACKENDS=http://10.1.75.53:3267,http://10.1.75.53:3268 deploy/run_gateway.sh 2>&1 | tee -a ~/hydrosage-gateway.log'
```

## Optional: add 2265 as a third instance

The Phase 1 API on 2265 runs `app.analyze_only`, the same entrypoint. After
a `git pull` and a restart with `deploy/run_api.sh` (step 1), it serves
`/analyzeArea` too and still answers `/analyzeContour` at the same URL. Add
`http://10.1.75.53:3265` to `GATEWAY_BACKENDS` and restart the gateway.

## Load test

From any machine that can reach the gateway (needs `pip install httpx`):

```bash
python loadtest/loadtest.py --url http://10.1.75.53:3266 --warm --levels 1,2,4,8 --seconds 60 --out results.json
```

It warms a small pool of areas once (one elevation download each, against
OpenTopography's 50-per-day quota) and then measures throughput, latency
percentiles, refusals and the spread across instances at each concurrency
level. Run it with two instances, then with three (the optional step above),
to measure how capacity scales.
