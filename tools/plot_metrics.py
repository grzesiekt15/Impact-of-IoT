#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcap", required=True)
    ap.add_argument("--lat", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--filter-n", nargs="*", help="Optional list of N values to include (e.g. 10 50 100).")
    ap.add_argument("--split-proto", action="store_true", help="Produce per-proto plots in subfolders.")
    ap.add_argument("--split-mode", action="store_true", help="Produce per-mode plots in subfolders.")
    ap.add_argument("--aggregate", action="store_true", help="Plot aggregated metrics per proto/mode/N with error bars.")
    args = ap.parse_args()

    outdir = Path(os.path.expanduser(args.outdir))
    outdir.mkdir(parents=True, exist_ok=True)

    pcap = pd.read_csv(os.path.expanduser(args.pcap))
    lat = pd.read_csv(os.path.expanduser(args.lat))

    # Przygotowanie czytelnych etykiet: proto_mode_N
    def mk_label(df, fallback_col="scenario"):
        proto = df.get("proto", pd.Series(dtype=str)).fillna("na").astype(str)
        mode = df.get("mode", pd.Series(dtype=str)).fillna("na").astype(str)
        n = df.get("N", pd.Series(dtype=str)).fillna("na").astype(str)
        if proto.isnull().all() or mode.isnull().all():
            return df[fallback_col].astype(str)
        return proto + "_" + mode + "_N" + n

    def infer_meta_from_name(name: str):
        name = str(name).lower()
        proto = None
        for p in ("http", "mqtt", "coap"):
            if p in name:
                proto = p
                break
        mode = None
        if "auth" in name:
            mode = "auth"
        if "open" in name and mode is None:
            mode = "open"
        import re
        N = None
        m = re.search(r"[ _-]n(\\d+)", name)
        if m:
            N = m.group(1)
        return proto, mode, N

    def ensure_meta(df: pd.DataFrame, source_col: str):
        if "proto" not in df.columns or "mode" not in df.columns or "N" not in df.columns:
            proto_list = []
            mode_list = []
            n_list = []
            for val in df[source_col]:
                proto, mode, N = infer_meta_from_name(val)
                proto_list.append(proto)
                mode_list.append(mode)
                n_list.append(N)
            df = df.copy()
            df["proto"] = df.get("proto", pd.Series(proto_list)).fillna(pd.Series(proto_list))
            df["mode"] = df.get("mode", pd.Series(mode_list)).fillna(pd.Series(mode_list))
            df["N"] = df.get("N", pd.Series(n_list)).fillna(pd.Series(n_list))
        return df

    def plot_aggregate(pcap_df: pd.DataFrame, lat_df: pd.DataFrame, odir: Path):
        odir.mkdir(parents=True, exist_ok=True)
        if pcap_df.empty:
            return
        pcap_df = ensure_meta(pcap_df, "scenario")
        pcap_df = pcap_df.dropna(subset=["proto", "mode", "N"])
        pcap_df["N"] = pd.to_numeric(pcap_df["N"], errors="coerce")
        metric = "bytes_per_sec_proto" if "bytes_per_sec_proto" in pcap_df.columns else "bytes_proto"
        agg = pcap_df.groupby(["proto", "mode", "N"]).agg(
            mean=(metric, "mean"),
            std=(metric, "std"),
            median=(metric, "median"),
            count=(metric, "count"),
        ).reset_index()
        agg["std"] = agg["std"].fillna(0)
        for proto in sorted(agg["proto"].dropna().unique()):
            sub = agg[agg["proto"] == proto]
            plt.figure(figsize=(8, 4))
            for mode in sorted(sub["mode"].dropna().unique()):
                s = sub[sub["mode"] == mode].sort_values("N")
                plt.errorbar(s["N"], s["mean"], yerr=s["std"], marker="o", label=mode, capsize=3)
            plt.xlabel("N")
            plt.ylabel(f"{metric} (mean ± std)")
            plt.title(f"{proto} throughput")
            plt.legend()
            plt.tight_layout()
            plt.savefig(odir / f"{proto}_{metric}_aggregate.png", dpi=200)
            plt.close()

        # Latency aggregate (if columns present)
        if not lat_df.empty:
            lat_df = ensure_meta(lat_df, "scenario")
            lat_df = lat_df.dropna(subset=["proto", "mode", "N"])
            lat_df["N"] = pd.to_numeric(lat_df["N"], errors="coerce")
            if "mean_latency_ms" in lat_df.columns:
                agg_lat = lat_df.groupby(["proto", "mode", "N"]).agg(
                    mean=("mean_latency_ms", "mean"),
                    std=("mean_latency_ms", "std"),
                    median=("mean_latency_ms", "median"),
                ).reset_index()
                agg_lat["std"] = agg_lat["std"].fillna(0)
                for proto in sorted(agg_lat["proto"].dropna().unique()):
                    sub = agg_lat[agg_lat["proto"] == proto]
                    plt.figure(figsize=(8, 4))
                    for mode in sorted(sub["mode"].dropna().unique()):
                        s = sub[sub["mode"] == mode].sort_values("N")
                        plt.errorbar(s["N"], s["mean"], yerr=s["std"], marker="o", label=mode, capsize=3)
                    plt.xlabel("N")
                    plt.ylabel("Mean latency (ms)")
                    plt.title(f"{proto} latency")
                    plt.legend()
                    plt.tight_layout()
                    plt.savefig(odir / f"{proto}_latency_aggregate.png", dpi=200)
                    plt.close()

            if "jitter_std_ms" in lat_df.columns:
                agg_jit = lat_df.dropna(subset=["jitter_std_ms"]).groupby(["proto", "mode", "N"]).agg(
                    mean=("jitter_std_ms", "mean"),
                    std=("jitter_std_ms", "std"),
                    median=("jitter_std_ms", "median"),
                ).reset_index()
                agg_jit["std"] = agg_jit["std"].fillna(0)
                for proto in sorted(agg_jit["proto"].dropna().unique()):
                    sub = agg_jit[agg_jit["proto"] == proto]
                    plt.figure(figsize=(8, 4))
                    for mode in sorted(sub["mode"].dropna().unique()):
                        s = sub[sub["mode"] == mode].sort_values("N")
                        plt.errorbar(s["N"], s["mean"], yerr=s["std"], marker="o", label=mode, capsize=3)
                    plt.xlabel("N")
                    plt.ylabel("Jitter std (ms)")
                    plt.title(f"{proto} jitter")
                    plt.legend()
                    plt.tight_layout()
                    plt.savefig(odir / f"{proto}_jitter_aggregate.png", dpi=200)
                    plt.close()

    # Wczytaj dane
    pcap_df = pd.read_csv(os.path.expanduser(args.pcap))
    lat_df = pd.read_csv(os.path.expanduser(args.lat))

    # Filtr N (jeśli jest kolumna N)
    if args.filter_n:
        if "N" in pcap_df.columns:
            pcap_df = pcap_df[pcap_df["N"].astype(str).isin(args.filter_n)]
        if "N" in lat_df.columns:
            lat_df = lat_df[lat_df["N"].astype(str).isin(args.filter_n)]

    if args.aggregate:
        plot_aggregate(pcap_df, lat_df, outdir)
    else:
        # Przygotowanie czytelnych etykiet: proto_mode_N
        def plot_set(pcap_df: pd.DataFrame, lat_df: pd.DataFrame, odir: Path):
            odir.mkdir(parents=True, exist_ok=True)

            if pcap_df.empty:
                return

            p = pcap_df.copy()
            p["label"] = mk_label(p, "scenario")
            p["N_num"] = pd.to_numeric(p.get("N"), errors="coerce")
            p = p.sort_values(["proto", "mode", "N_num"])

            plt.figure(figsize=(10, 5))
            plt.bar(p["label"], p["bytes_per_sec_proto"])
            plt.ylabel("Bytes/sec (proto)")
            plt.xticks(rotation=60, ha="right", fontsize=8)
            plt.tight_layout()
            plt.savefig(odir / "bytes_per_sec_proto.png", dpi=200)
            plt.close()

            l = lat_df[lat_df["count"] > 0].copy() if "count" in lat_df.columns else lat_df.copy()
            if l.empty:
                return
            l["label"] = mk_label(l, "scenario")
            l["mean_latency_ms"] = pd.to_numeric(l["mean_latency_ms"], errors="coerce")
            l = l.dropna(subset=["mean_latency_ms"])
            sort_cols = [c for c in ("proto", "mode", "N") if c in l.columns]
            if sort_cols:
                l = l.sort_values(sort_cols, na_position="last")

            plt.figure(figsize=(12, 6))
            plt.bar(l["label"], l["mean_latency_ms"])
            plt.ylabel("Mean latency (ms)")
            plt.xticks(rotation=75, ha="right", fontsize=7)
            plt.tight_layout()
            plt.savefig(odir / "mean_latency_ms.png", dpi=200)
            plt.close()

            if "jitter_std_ms" in l.columns:
                l_j = l.dropna(subset=["jitter_std_ms"])
                l_j["jitter_std_ms"] = pd.to_numeric(l_j["jitter_std_ms"], errors="coerce")
                l_j = l_j.dropna(subset=["jitter_std_ms"])
                if not l_j.empty:
                    plt.figure(figsize=(12, 6))
                    plt.bar(l_j["label"], l_j["jitter_std_ms"])
                    plt.ylabel("Jitter (std dev, ms)")
                    plt.xticks(rotation=75, ha="right", fontsize=7)
                    plt.tight_layout()
                    plt.savefig(odir / "jitter_std_ms.png", dpi=200)
                    plt.close()

        # Główne wykresy
        plot_set(pcap_df, lat_df, outdir)

        # Podział per proto
        if args.split_proto and "proto" in pcap_df.columns:
            for proto in sorted(pcap_df["proto"].dropna().unique()):
                p_sub = pcap_df[pcap_df["proto"] == proto]
                l_sub = lat_df.copy()
                if "proto" in l_sub.columns:
                    l_sub = l_sub[l_sub["proto"] == proto]
                else:
                    l_sub = l_sub[l_sub["scenario"].str.contains(proto, case=False, na=False)]
                plot_set(p_sub, l_sub, outdir / f"proto_{proto}")

        # Podział per mode
        if args.split_mode and "mode" in pcap_df.columns:
            for mode in sorted(pcap_df["mode"].dropna().unique()):
                p_sub = pcap_df[pcap_df["mode"] == mode]
                l_sub = lat_df.copy()
                if "mode" in l_sub.columns:
                    l_sub = l_sub[l_sub["mode"] == mode]
                else:
                    l_sub = l_sub[l_sub["scenario"].str.contains(mode, case=False, na=False)]
                plot_set(p_sub, l_sub, outdir / f"mode_{mode}")

    print(f"Saved plots to: {outdir}")

if __name__ == "__main__":
    main()
