#!/usr/bin/env python3
"""
plot_metrics_scientific.py

Wykresy "pod pracę" + różne style/wnioski:
F1: RTT median vs N — linie + wstęga (mean±SD), 3 panele (proto)
F2: RTT p95 vs N — inne style linii (ogon opóźnień), 3 panele
F3: Jitter vs N — linia mean±SD + punkty replikacji, 3 panele
F4: Bytes/sec vs N — area + SD, 3 panele
F5: Δ RTT (AUTH−OPEN) vs N — słupki, 3 panele
F6: Dumbbell RTT dla N=100 — OPEN vs AUTH per protokół
F7: Dumbbell throughput (KB/s) dla N=100 — OPEN vs AUTH per protokół

Uruchom:
  python plot_metrics_scientific.py --lat latency_metrics.csv --pcap pcap_metrics.csv --outdir results/plots
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ---- jeśli masz inne nazwy scenariuszy, edytuj regexy ----
RE_MODE = re.compile(r"\b(open|auth)\b", re.I)
RE_PROTO = re.compile(r"\b(http|mqtt|coap)\b", re.I)
RE_N = re.compile(r"(?:^|[_\-])n(\d+)(?:[_\-]|$)", re.I)
RE_REP = re.compile(r"(?:^|[_\-])rep(\d+)(?:[_\-]|$)", re.I)

PROTO_ORDER = ["http", "mqtt", "coap"]
MODE_ORDER = ["open", "auth"]
N_ORDER = [10, 50, 100]

# Kolory (color-blind friendly) + style
COL = {"open": "#0072B2", "auth": "#D55E00", "unknown": "#7f7f7f"}
LINESTYLE = {"open": "-", "auth": "--"}
MARKER = {"open": "o", "auth": "s"}
ALPHA_BAND = 0.18

def parse_meta(s: str):
    s = str(s)
    m_mode = RE_MODE.search(s)
    m_proto = RE_PROTO.search(s)
    m_n = RE_N.search(s.lower())
    m_rep = RE_REP.search(s.lower())
    mode = m_mode.group(1).lower() if m_mode else None
    proto = m_proto.group(1).lower() if m_proto else None
    N = int(m_n.group(1)) if m_n else None
    rep = int(m_rep.group(1)) if m_rep else None
    return mode, proto, N, rep

def set_rcparams():
    plt.rcParams.update({
        "figure.dpi": 120,
        "axes.grid": True,
        "grid.linestyle": "--",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.35,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "semibold",
        "axes.labelsize": 10,
        "axes.titlesize": 12,
        "legend.frameon": True,
        "legend.framealpha": 0.9,
        "legend.fontsize": 9,
    })

def savefig(path: Path):
    plt.tight_layout()
    plt.savefig(path, dpi=260, bbox_inches="tight")
    plt.close()

def ensure_order(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "proto" in df.columns:
        df["proto"] = pd.Categorical(df["proto"], categories=PROTO_ORDER, ordered=True)
    if "mode" in df.columns:
        df["mode"] = pd.Categorical(df["mode"], categories=MODE_ORDER, ordered=True)
    if "N" in df.columns:
        df["N"] = pd.Categorical(df["N"], categories=N_ORDER, ordered=True)
    return df.sort_values([c for c in ["proto","mode","N"] if c in df.columns])

def prep_latency_rep(lat_csv: Path) -> pd.DataFrame:
    raw = pd.read_csv(lat_csv)
    rows = []
    for _, r in raw.iterrows():
        mode, proto, N, rep = parse_meta(r.get("scenario",""))
        if mode is None or proto is None or N is None or rep is None:
            continue
        count = r.get("count", np.nan)
        if pd.notna(count) and float(count) <= 0:
            continue
        rows.append({
            "mode": mode, "proto": proto, "N": int(N), "rep": int(rep),
            "median_latency_ms": r.get("median_latency_ms", np.nan),
            "p95_latency_ms": r.get("p95_latency_ms", np.nan),
            "jitter_std_ms": r.get("jitter_std_ms", np.nan),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("Nie sparsowałem nic z latency_metrics.csv — sprawdź nazwy scenario / regexy.")
    # rep-level (średnia po klientach, jeśli są osobne wpisy)
    return (df.groupby(["mode","proto","N","rep"], as_index=False)
              .agg(median_latency_ms=("median_latency_ms","mean"),
                   p95_latency_ms=("p95_latency_ms","mean"),
                   jitter_std_ms=("jitter_std_ms","mean")))

def prep_pcap_rep(pcap_csv: Path) -> pd.DataFrame:
    raw = pd.read_csv(pcap_csv)
    if "bytes_per_sec_proto" not in raw.columns:
        raise SystemExit("pcap_metrics.csv musi mieć kolumnę bytes_per_sec_proto")
    rows = []
    for _, r in raw.iterrows():
        mode, proto, N, rep = parse_meta(r.get("scenario",""))
        # fallback jeśli masz kolumny mode/proto/N/rep
        mode = mode or (str(r.get("mode")).lower() if pd.notna(r.get("mode")) else None)
        proto = proto or (str(r.get("proto")).lower() if pd.notna(r.get("proto")) else None)
        N = N or (int(r.get("N")) if pd.notna(r.get("N")) else None)
        rep = rep or (int(r.get("rep")) if pd.notna(r.get("rep")) else None)
        if mode is None or proto is None or N is None:
            continue
        rep = rep if rep is not None else 1
        rows.append({"mode": mode, "proto": proto, "N": int(N), "rep": int(rep),
                     "bytes_per_sec": float(r["bytes_per_sec_proto"])})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("Nie sparsowałem nic z pcap_metrics.csv — sprawdź scenario/kolumny.")
    return (df.groupby(["mode","proto","N","rep"], as_index=False)
              .agg(bytes_per_sec=("bytes_per_sec","mean")))

def summarize(rep_df: pd.DataFrame, metric: str) -> pd.DataFrame:
    return (rep_df.groupby(["mode","proto","N"], as_index=False)
                  .agg(mean=(metric,"mean"), sd=(metric,"std"), reps=("rep","nunique")))

def facet_lines_with_band(summary_df: pd.DataFrame, ylabel: str, title: str, out: Path, style_map):
    protos = [p for p in PROTO_ORDER if p in summary_df["proto"].unique().tolist()]
    fig, axes = plt.subplots(1, len(protos), figsize=(12, 3.7), sharey=True)
    if len(protos) == 1:
        axes = [axes]
    for ax, proto in zip(axes, protos):
        sub = summary_df[summary_df["proto"] == proto]
        for mode in [m for m in MODE_ORDER if m in sub["mode"].unique().tolist()]:
            s2 = sub[sub["mode"] == mode]
            x = s2["N"].astype(int).values
            y = s2["mean"].astype(float).values
            sd = s2["sd"].astype(float).values
            ax.plot(x, y, linestyle=style_map.get(mode, LINESTYLE.get(mode,"-")),
                    marker=MARKER.get(mode,"o"), linewidth=2.4, markersize=6,
                    color=COL.get(mode,COL["unknown"]), label=mode.upper())
            if np.any(~np.isnan(sd)):
                ax.fill_between(x, y-sd, y+sd, color=COL.get(mode,COL["unknown"]), alpha=ALPHA_BAND)
        ax.set_title(proto.upper())
        ax.set_xlabel("Liczba klientów (N)")
        ax.set_xticks(N_ORDER)
    axes[0].set_ylabel(ylabel)
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.suptitle(title, y=1.03)
    fig.legend(handles, labels, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.18))
    savefig(out)

def facet_lines_with_rep_points(rep_df: pd.DataFrame, summary_df: pd.DataFrame, metric: str, ylabel: str, title: str, out: Path):
    protos = [p for p in PROTO_ORDER if p in rep_df["proto"].unique().tolist()]
    fig, axes = plt.subplots(1, len(protos), figsize=(12, 3.7), sharey=True)
    if len(protos) == 1:
        axes = [axes]
    rng = np.random.default_rng(0)
    for ax, proto in zip(axes, protos):
        sub_rep = rep_df[rep_df["proto"] == proto]
        sub_sum = summary_df[summary_df["proto"] == proto]
        for mode in [m for m in MODE_ORDER if m in sub_rep["mode"].unique().tolist()]:
            srep = sub_rep[sub_rep["mode"] == mode]
            for N in N_ORDER:
                pts = srep[srep["N"].astype(int) == N][metric].dropna().astype(float).values
                if pts.size == 0: 
                    continue
                jit = rng.normal(0, 0.9, size=pts.size)
                ax.scatter(np.full(pts.size, N)+jit, pts, s=30, alpha=0.85,
                           color=COL.get(mode,COL["unknown"]))
        for mode in [m for m in MODE_ORDER if m in sub_sum["mode"].unique().tolist()]:
            s2 = sub_sum[sub_sum["mode"] == mode]
            ax.errorbar(s2["N"].astype(int).values, s2["mean"].astype(float).values,
                        yerr=s2["sd"].astype(float).values, linestyle=LINESTYLE.get(mode,"-"),
                        marker=MARKER.get(mode,"o"), linewidth=2.4, markersize=6, capsize=4,
                        color=COL.get(mode,COL["unknown"]), label=mode.upper())
        ax.set_title(proto.upper())
        ax.set_xlabel("Liczba klientów (N)")
        ax.set_xticks(N_ORDER)
    axes[0].set_ylabel(ylabel)
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.suptitle(title, y=1.03)
    fig.legend(handles, labels, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.18))
    savefig(out)

def facet_area_bytes(summary_df: pd.DataFrame, out: Path):
    protos = [p for p in PROTO_ORDER if p in summary_df["proto"].unique().tolist()]
    fig, axes = plt.subplots(1, len(protos), figsize=(12, 3.7), sharey=True)
    if len(protos) == 1:
        axes = [axes]
    for ax, proto in zip(axes, protos):
        sub = summary_df[summary_df["proto"] == proto]
        for mode in [m for m in MODE_ORDER if m in sub["mode"].unique().tolist()]:
            s2 = sub[sub["mode"] == mode]
            x = s2["N"].astype(int).values
            y = s2["mean"].astype(float).values / 1024.0
            sd = s2["sd"].astype(float).values / 1024.0
            ax.plot(x, y, linestyle=LINESTYLE.get(mode,"-"), marker=MARKER.get(mode,"o"),
                    linewidth=2.4, markersize=6, color=COL.get(mode,COL["unknown"]), label=mode.upper())
            ax.fill_between(x, 0, y, color=COL.get(mode,COL["unknown"]), alpha=0.10)
            ax.fill_between(x, y-sd, y+sd, color=COL.get(mode,COL["unknown"]), alpha=0.12)
        ax.set_title(proto.upper())
        ax.set_xlabel("Liczba klientów (N)")
        ax.set_xticks(N_ORDER)
    axes[0].set_ylabel("KB/s")
    fig.suptitle("F4: PCAP throughput (KB/s) vs N — area + SD", y=1.03)
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.18))
    savefig(out)

def delta_bars(summary_df: pd.DataFrame, ylabel: str, title: str, out: Path):
    piv = summary_df.pivot_table(index=["proto","N"], columns="mode", values="mean").reset_index()
    if "open" not in piv.columns or "auth" not in piv.columns:
        return
    piv["delta"] = piv["auth"] - piv["open"]
    piv = ensure_order(piv)
    protos = [p for p in PROTO_ORDER if p in piv["proto"].unique().tolist()]
    fig, axes = plt.subplots(1, len(protos), figsize=(12, 3.6), sharey=True)
    if len(protos) == 1:
        axes = [axes]
    for ax, proto in zip(axes, protos):
        sub = piv[piv["proto"] == proto]
        x = np.arange(len(N_ORDER))
        vals = []
        for N in N_ORDER:
            v = sub[sub["N"].astype(int) == N]["delta"]
            vals.append(float(v.iloc[0]) if len(v) else np.nan)
        ax.axhline(0, linewidth=1.2, color="#444444")
        ax.bar(x, vals, width=0.62, color="#4C78A8")
        ax.set_xticks(x, [str(n) for n in N_ORDER])
        ax.set_title(proto.upper())
        ax.set_xlabel("N")
    axes[0].set_ylabel(ylabel)
    fig.suptitle(title, y=1.03)
    savefig(out)

def dumbbell_open_auth(summary_df: pd.DataFrame, ylabel: str, title: str, out: Path, N_focus=100, scale_kb=False):
    sub = summary_df[summary_df["N"].astype(int) == int(N_focus)]
    piv = sub.pivot_table(index="proto", columns="mode", values="mean").reset_index()
    if "open" not in piv.columns or "auth" not in piv.columns:
        return
    piv = ensure_order(piv)
    protos = [p for p in PROTO_ORDER if p in piv["proto"].unique().tolist()]
    y = np.arange(len(protos))
    open_v = piv.set_index("proto").loc[protos, "open"].astype(float).values
    auth_v = piv.set_index("proto").loc[protos, "auth"].astype(float).values
    if scale_kb:
        open_v /= 1024.0
        auth_v /= 1024.0
    plt.figure(figsize=(8.2, 3.6))
    for i, proto in enumerate(protos):
        plt.plot([open_v[i], auth_v[i]], [i, i], color="#666666", linewidth=2.0, alpha=0.85)
        plt.scatter(open_v[i], i, color=COL["open"], s=70, zorder=3, label="OPEN" if i == 0 else None)
        plt.scatter(auth_v[i], i, color=COL["auth"], s=70, zorder=3, label="AUTH" if i == 0 else None)
    plt.yticks(y, [p.upper() for p in protos])
    plt.xlabel(ylabel)
    plt.title(title)
    plt.grid(True, axis="x")
    plt.legend(loc="best")
    savefig(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", required=True)
    ap.add_argument("--pcap", required=True)
    ap.add_argument("--outdir", default="results/plots")
    args = ap.parse_args()

    set_rcparams()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rep_lat = prep_latency_rep(Path(args.lat))
    rep_pcap = prep_pcap_rep(Path(args.pcap))

    lat_med_sum = ensure_order(summarize(rep_lat, "median_latency_ms"))
    lat_p95_sum = ensure_order(summarize(rep_lat, "p95_latency_ms"))
    jit_sum = ensure_order(summarize(rep_lat, "jitter_std_ms"))
    bytes_sum = ensure_order(summarize(rep_pcap, "bytes_per_sec"))

    lat_med_sum.to_csv(outdir / "summary_latency_median.csv", index=False)
    lat_p95_sum.to_csv(outdir / "summary_latency_p95.csv", index=False)
    jit_sum.to_csv(outdir / "summary_jitter_std.csv", index=False)
    bytes_sum.to_csv(outdir / "summary_bytes_per_sec.csv", index=False)

    facet_lines_with_band(lat_med_sum,
        ylabel="RTT median [ms] (mean±SD z 3 rep)",
        title="F1: RTT (median) vs N — OPEN vs AUTH",
        out=outdir / "F1_rtt_median_vs_N.png",
        style_map={"open": "-", "auth": "--"}
    )

    facet_lines_with_band(lat_p95_sum,
        ylabel="RTT p95 [ms] (mean±SD z 3 rep)",
        title="F2: RTT (p95) vs N — ogon opóźnień (inne style)",
        out=outdir / "F2_rtt_p95_vs_N.png",
        style_map={"open": ":", "auth": "-."}
    )

    facet_lines_with_rep_points(rep_lat, jit_sum, "jitter_std_ms",
        ylabel="Jitter STD [ms] (kropki=replikacje; linia=mean±SD)",
        title="F3: Jitter vs N — OPEN vs AUTH",
        out=outdir / "F3_jitter_vs_N_points.png"
    )

    facet_area_bytes(bytes_sum, outdir / "F4_bytes_vs_N_area.png")

    delta_bars(lat_med_sum,
        ylabel="Δ RTT median [ms] (AUTH − OPEN)",
        title="F5: Narzut AUTH na RTT (Δ) vs N",
        out=outdir / "F5_delta_rtt_median.png"
    )

    dumbbell_open_auth(lat_med_sum,
        ylabel="RTT median [ms]",
        title="F6: OPEN vs AUTH przy N=100 (RTT) — dumbbell",
        out=outdir / "F6_dumbbell_rtt_N100.png",
        N_focus=100, scale_kb=False
    )

    dumbbell_open_auth(bytes_sum,
        ylabel="KB/s",
        title="F7: OPEN vs AUTH przy N=100 (Throughput) — dumbbell",
        out=outdir / "F7_dumbbell_bytes_N100.png",
        N_focus=100, scale_kb=True
    )

    print("[OK] Zapisano:", outdir.resolve())

if __name__ == "__main__":
    main()
