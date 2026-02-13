#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from statistics import mean, median, pstdev

import pandas as pd

RE_MODE = re.compile(r"(?:^|[_/\\-])(open|auth)(?:[_/\\-]|$)", re.I)
RE_PROTO = re.compile(r"(?:^|[_/\\-])(http|mqtt|coap)(?:[_/\\-]|$)", re.I)
RE_N = re.compile(r"(?:^|[_/\\-])n(\\d+)(?:[_/\\-]|$)", re.I)
RE_REP = re.compile(r"(?:^|[_/\\-])rep(\\d+)(?:[_/\\-]|$)", re.I)


def parse_meta(path: Path):
    s = str(path).lower()
    m_mode = RE_MODE.search(s)
    m_proto = RE_PROTO.search(s)
    m_n = RE_N.search(s)
    m_rep = RE_REP.search(s)
    mode = m_mode.group(1) if m_mode else None
    proto = m_proto.group(1) if m_proto else None
    n = int(m_n.group(1)) if m_n else None
    rep = int(m_rep.group(1)) if m_rep else None
    return mode, proto, n, rep


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    idx = int(round((len(sorted_vals) - 1) * p))
    return float(sorted_vals[idx])


def main():
    ap = argparse.ArgumentParser(description="Aggregate RTT/jitter from raw client CSVs.")
    ap.add_argument("--root", required=True, help="Root with results (recursive).")
    ap.add_argument("--out", required=True, help="Output latency summary CSV (ms).")
    ap.add_argument("--out-jitter", required=True, help="Output jitter summary CSV (ms).")
    ap.add_argument("--outlier-mult", type=float, default=10.0, help="Drop samples > mult * median per client.")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.out).resolve()
    out_jitter = Path(args.out_jitter).resolve()

    by = {}
    file_count = 0
    for path in root.rglob("metrics_*_id*.csv"):
        mode, proto, n, rep = parse_meta(path)
        if mode is None or proto is None or n is None or rep is None:
            continue
        df = pd.read_csv(path)
        if "rtt" not in df.columns:
            continue
        rtt = pd.to_numeric(df["rtt"], errors="coerce").dropna().tolist()
        if not rtt:
            continue
        # rtt in seconds -> ms
        rtt_ms = [v * 1000.0 for v in rtt]
        med = median(rtt_ms)
        if med > 0 and args.outlier_mult > 0:
            rtt_ms = [v for v in rtt_ms if v <= args.outlier_mult * med]
        if not rtt_ms:
            continue
        key = (mode, proto, n)
        by.setdefault(key, []).extend(rtt_ms)
        file_count += 1

    if not by:
        raise SystemExit("No RTT samples found under root.")

    out.parent.mkdir(parents=True, exist_ok=True)
    out_jitter.parent.mkdir(parents=True, exist_ok=True)

    lat_rows = []
    jit_rows = []
    for (mode, proto, n), vals in sorted(by.items(), key=lambda x: (x[0][1], x[0][0], x[0][2])):
        vals_sorted = sorted(vals)
        lat_rows.append({
            "mode": mode,
            "proto": proto,
            "N": n,
            "mean_rtt_ms": round(mean(vals_sorted), 6),
            "median_ms": round(median(vals_sorted), 6),
            "p95_ms": round(percentile(vals_sorted, 0.95), 6),
            "p99_ms": round(percentile(vals_sorted, 0.99), 6),
        })
        jitter = pstdev(vals_sorted) if len(vals_sorted) >= 2 else 0.0
        jit_rows.append({
            "mode": mode,
            "proto": proto,
            "N": n,
            "mean_jitter_ms": round(jitter, 6),
        })

    pd.DataFrame(lat_rows).to_csv(out, index=False)
    pd.DataFrame(jit_rows).to_csv(out_jitter, index=False)
    print(f"Wrote {out} and {out_jitter}")


if __name__ == "__main__":
    main()
