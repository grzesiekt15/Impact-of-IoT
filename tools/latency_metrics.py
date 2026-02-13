#!/usr/bin/env python3
import argparse
import csv
import os
import re
from pathlib import Path
from statistics import mean, median, pstdev
from typing import List, Optional, Dict, Tuple

LOG_EXTS = (".log", ".txt", ".csv")

# Regexy łapiące typowe zapisy RTT/latency (ms)
LAT_PATTERNS = [
    re.compile(r"\b(?:latency|rtt)\s*[:=]\s*([0-9]*\.?[0-9]+)\s*ms\b", re.I),
    re.compile(r"\bRTT[_\s-]*ms\s*[:=]\s*([0-9]*\.?[0-9]+)\b", re.I),
    re.compile(r"\b([0-9]*\.?[0-9]+)\s*ms\b.*\b(?:latency|rtt)\b", re.I),
]

# Timeout/error patterns (opcjonalnie)
TIMEOUT_PAT = re.compile(r"\b(timeout|timed\s*out)\b", re.I)
ERROR_PAT = re.compile(r"\b(error|failed|exception)\b", re.I)

def percentiles(sorted_vals: List[float], ps: List[float]) -> Dict[str, Optional[float]]:
    out = {}
    n = len(sorted_vals)
    for p in ps:
        if n == 0:
            out[f"p{int(p*100)}"] = None
            continue
        idx = int(round((n - 1) * p))
        out[f"p{int(p*100)}"] = float(sorted_vals[idx])
    return out

def jitter_mad(vals: List[float]) -> Optional[float]:
    if len(vals) < 2:
        return None
    diffs = [abs(vals[i] - vals[i-1]) for i in range(1, len(vals))]
    return float(mean(diffs)) if diffs else None

def parse_latency_from_csv(path: Path) -> Tuple[List[float], int, int]:
    """Return (latencies_ms, timeouts, errors) from CSV if possible."""
    lat: List[float] = []
    timeouts = 0
    errors = 0
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        # szukamy sensownej kolumny
        candidates = [c for c in (reader.fieldnames or [])]
        col = None
        for name in candidates:
            ln = name.lower()
            if ln in ("latency_ms", "rtt_ms", "rtt", "latency"):
                col = name
                break
        if col is None:
            return [], 0, 0

        for row in reader:
            v = (row.get(col) or "").strip()
            if not v:
                continue
            try:
                # CSV RTT is recorded in seconds in this project; convert to ms
                lat.append(float(v) * 1000.0)
            except ValueError:
                pass
            # opcjonalnie błędy
            status = " ".join(str(x) for x in row.values())
            if TIMEOUT_PAT.search(status):
                timeouts += 1
            if ERROR_PAT.search(status):
                errors += 1
    return lat, timeouts, errors

def parse_latency_from_text(path: Path) -> Tuple[List[float], int, int]:
    lat: List[float] = []
    timeouts = 0
    errors = 0
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if TIMEOUT_PAT.search(line):
                timeouts += 1
            if ERROR_PAT.search(line):
                errors += 1

            s = line.strip()
            for pat in LAT_PATTERNS:
                m = pat.search(s)
                if m:
                    try:
                        lat.append(float(m.group(1)))
                    except ValueError:
                        pass
                    break
    return lat, timeouts, errors

def guess_scenario_from_path(path: Path) -> str:
    # np. paper_run_open/http/N100/rep1/client.log
    # -> open_http_N100_rep1_client
    parts = [p.lower() for p in path.parts]
    mode = "open" if "paper_run_open" in parts or "open" in parts else ("auth" if "paper_run_auth" in parts or "auth" in parts else "unknown")

    proto = next((x for x in ["http","mqtt","coap"] if x in parts), "unknown")

    N = next((x for x in parts if x.startswith("n") and x[1:].isdigit()), "N?")
    rep = next((x for x in parts if x.startswith("rep") and x[3:].isdigit()), "rep?")

    name = path.stem.lower()
    return f"{mode}_{proto}_{N}_{rep}_{name}"

def analyze_file(path: Path) -> Dict[str, object]:
    if path.suffix.lower() == ".csv":
        lat, to, err = parse_latency_from_csv(path)
    else:
        lat, to, err = parse_latency_from_text(path)

    # Drop extreme outliers: anything > 10x median for this client
    if lat:
        med_raw = float(median(lat))
        if med_raw > 0:
            lat = [v for v in lat if v <= 10.0 * med_raw]

    lat_sorted = sorted(lat)
    n = len(lat_sorted)

    if n == 0:
        return {
            "scenario": guess_scenario_from_path(path),
            "log_path": str(path),
            "count": 0,
            "mean_latency_ms": None,
            "median_latency_ms": None,
            "min_latency_ms": None,
            "max_latency_ms": None,
            "p90_latency_ms": None,
            "p95_latency_ms": None,
            "p99_latency_ms": None,
            "jitter_std_ms": None,
            "jitter_mad_ms": None,
            "outliers_3sigma": None,
            "timeouts": to,
            "errors": err,
            "loss_rate_pct": None,
        }

    mu = float(mean(lat_sorted))
    med = float(median(lat_sorted))
    sd = float(pstdev(lat_sorted)) if n >= 2 else 0.0
    p = percentiles(lat_sorted, [0.90, 0.95, 0.99])
    out3 = sum(1 for v in lat_sorted if v > mu + 3*sd) if n >= 2 else 0
    jm = jitter_mad(lat)

    loss = None
    denom = n + to
    if denom > 0:
        loss = 100.0 * to / denom

    return {
        "scenario": guess_scenario_from_path(path),
        "log_path": str(path),
        "count": n,
        "mean_latency_ms": round(mu, 6),
        "median_latency_ms": round(med, 6),
        "min_latency_ms": round(lat_sorted[0], 6),
        "max_latency_ms": round(lat_sorted[-1], 6),
        "p90_latency_ms": round(p["p90"], 6),
        "p95_latency_ms": round(p["p95"], 6),
        "p99_latency_ms": round(p["p99"], 6),
        "jitter_std_ms": round(sd, 6),
        "jitter_mad_ms": round(jm, 6) if jm is not None else None,
        "outliers_3sigma": int(out3),
        "timeouts": int(to),
        "errors": int(err),
        "loss_rate_pct": round(loss, 6) if loss is not None else None,
    }

def find_logs(root: Path) -> List[Path]:
    out = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in LOG_EXTS:
            out.append(p)
    return sorted(out)

def main():
    ap = argparse.ArgumentParser(description="Extract latency/jitter metrics from logs -> CSV")
    ap.add_argument("--root", required=True, help="Root folder with logs (recursive).")
    ap.add_argument("--out", required=True, help="Output CSV path.")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.root)).resolve()
    out_csv = Path(os.path.expanduser(args.out)).resolve()

    logs = find_logs(root)
    if not logs:
        raise SystemExit(f"No log/csv/txt files found under {root}")

    rows = []
    for f in logs:
        row = analyze_file(f)
        # bierzemy tylko te pliki, gdzie znaleziono choć 1 pomiar ALBO są timeouty/błędy
        if row["count"] > 0 or (row["timeouts"] or 0) > 0 or (row["errors"] or 0) > 0:
            rows.append(row)

    fieldnames = [
        "scenario","log_path","count",
        "mean_latency_ms","median_latency_ms","min_latency_ms","max_latency_ms",
        "p90_latency_ms","p95_latency_ms","p99_latency_ms",
        "jitter_std_ms","jitter_mad_ms","outliers_3sigma",
        "timeouts","errors","loss_rate_pct"
    ]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Saved: {out_csv} | rows: {len(rows)}")

if __name__ == "__main__":
    main()
