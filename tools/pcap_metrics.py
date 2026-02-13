#!/usr/bin/env python3
import argparse
import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ports used in your lab setup
PROTO_FILTERS = {
    "coap": ("udp.port==5683", "UDP/5683"),
    "mqtt": ("tcp.port==1883", "TCP/1883"),
    "http": ("tcp.port==5000", "TCP/5000"),
}

PCAP_EXTS = (".pcap", ".pcapng")


@dataclass
class CaptureStats:
    duration_s: float
    frames: int
    bytes: int


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command and capture stdout/stderr."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout, p.stderr


def require_tshark() -> None:
    rc, out, err = run_cmd(["tshark", "-v"])
    if rc != 0:
        print("ERROR: tshark is not available. Install it with: sudo apt install -y tshark", file=sys.stderr)
        sys.exit(2)


def parse_io_stat_output(text: str) -> Optional[CaptureStats]:
    """
    Parse output of: tshark -r FILE -q -z io,stat,0[,FILTER]
    We extract Duration, Frames, Bytes from the "=== General ===" section.
    """
    # tshark output varies slightly between versions; be tolerant
    # Example lines:
    #   Duration: 13.623 secs
    #   Frames: 2008
    #   Bytes: 2167205
    dur = None
    frames = None
    byt = None

    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^Duration:\s*([0-9]*\.?[0-9]+)\s*(?:sec|secs|seconds)\b", line)
        if m:
            dur = float(m.group(1))
            continue
        m = re.match(r"^Frames:\s*([0-9]+)\s*$", line)
        if m:
            frames = int(m.group(1))
            continue
        m = re.match(r"^Bytes:\s*([0-9]+)\s*$", line)
        if m:
            byt = int(m.group(1))
            continue

    if dur is None or frames is None or byt is None:
        return None
    return CaptureStats(duration_s=dur, frames=frames, bytes=byt)


def tshark_io_stat(pcap: Path, display_filter: Optional[str] = None) -> CaptureStats:
    cmd = ["tshark", "-r", str(pcap), "-q", "-z", "io,stat,0"]
    if display_filter:
        # NOTE: io,stat expects exactly ONE filter argument (no labels)
        cmd[-1] = f"io,stat,0,{display_filter}"
    rc, out, err = run_cmd(cmd)
    # tshark often prints to stderr; merge both
    text = (out or "") + "\n" + (err or "")
    stats = parse_io_stat_output(text)
    if rc != 0 or stats is None:
        raise RuntimeError(f"tshark io,stat failed for {pcap.name} (filter={display_filter}). Output:\n{text}")
    return stats


def tshark_frame_lengths(pcap: Path, display_filter: str) -> List[int]:
    """
    Return list of frame lengths (ints) for packets matching display_filter.
    Uses: tshark -Y FILTER -T fields -e frame.len
    """
    cmd = [
        "tshark",
        "-r", str(pcap),
        "-Y", display_filter,
        "-T", "fields",
        "-e", "frame.len",
    ]
    rc, out, err = run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"tshark frame.len failed for {pcap.name} (filter={display_filter}).\n{err}")
    lens: List[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lens.append(int(line))
        except ValueError:
            pass
    return lens


def percentile(sorted_vals: List[int], p: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if p <= 0:
        return float(sorted_vals[0])
    if p >= 1:
        return float(sorted_vals[-1])
    idx = int(round((len(sorted_vals) - 1) * p))
    return float(sorted_vals[idx])


def guess_meta_from_path(pcap: Path) -> Dict[str, Optional[str]]:
    """
    Extract scenario metadata from filename/path:
    - mode: open/auth
    - proto: coap/http/mqtt
    - N: from N\d+
    - payload_size: from payload\d+ or P\d+
    """
    s_full = str(pcap).lower()
    name = pcap.name.lower()
    parts = [p.lower() for p in pcap.parts]

    mode = None
    # prefer the nearest path element that clearly states open/auth
    for part in reversed(parts):
        if part in ("open", "auth"):
            mode = part
            break
        if mode is None:
            if re.search(r"\bopen\b", part):
                mode = "open"
            elif re.search(r"\bauth\b", part):
                mode = "auth"
        if mode:
            break
    # fallback to filename if still unknown
    if mode is None:
        if "open" in name:
            mode = "open"
        elif "auth" in name:
            mode = "auth"

    proto = None
    for k in ("coap", "mqtt", "http"):
        if k in s_full:
            proto = k
            break

    n = None
    m = re.search(r"(?:^|[_\-])n(\d+)(?:[_\-]|\.|$)", s_full)
    if m:
        n = m.group(1)

    payload = None
    m = re.search(r"(?:payload|pl|p)(\d+)", s_full)
    if m:
        payload = m.group(1)

    return {"mode": mode, "proto": proto, "N": n, "payload_size": payload}


def ensure_csv_header(csv_path: Path, fieldnames: List[str]) -> None:
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()


def tshark_basic_stats(pcap: Path, display_filter: Optional[str] = None) -> CaptureStats:
    """
    Robust stats from fields (works across tshark versions):
    - frames: count rows
    - bytes: sum frame.len
    - duration: max frame.time_relative
    """
    cmd = ["tshark", "-r", str(pcap)]
    if display_filter:
        cmd += ["-Y", display_filter]
    cmd += ["-T", "fields", "-e", "frame.len", "-e", "frame.time_relative"]

    rc, out, err = run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"tshark fields failed for {pcap.name} (filter={display_filter}).\n{err}")

    frames = 0
    total_bytes = 0
    max_t = 0.0

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            flen = int(parts[0]) if parts[0] else 0
            t = float(parts[1]) if parts[1] else 0.0
        except ValueError:
            continue
        frames += 1
        total_bytes += flen
        if t > max_t:
            max_t = t

    return CaptureStats(duration_s=max_t, frames=frames, bytes=total_bytes)



def compute_metrics_for_pcap(pcap: Path) -> Dict[str, object]:
    meta = guess_meta_from_path(pcap)

    # Total capture stats (all traffic)
    total = tshark_basic_stats(pcap, None)

    # Decide which protocol filter to use
    proto = meta["proto"]
    proto_filter = None
    proto_label = None

    if proto in PROTO_FILTERS:
        proto_filter, proto_label = PROTO_FILTERS[proto]
    else:
        # Fallback: compute bytes for each known port and pick the biggest one
        best = None  # (bytes, proto, filter, label)
        for p, (flt, lbl) in PROTO_FILTERS.items():
            try:
                st = tshark_basic_stats(pcap, flt)
                cand = (st.bytes, p, flt, lbl)
                if best is None or cand[0] > best[0]:
                    best = cand
            except Exception:
                continue
        if best:
            _, proto, proto_filter, proto_label = best
        else:
            proto = None

    proto_stats = None
    if proto_filter:
        proto_stats = tshark_basic_stats(pcap, proto_filter)

    # Frame length stats for proto filter (port-based, works even if dissector doesn't)
    avg_len = None
    p95_len = None
    p99_len = None
    frame_count_port = None

    if proto_filter:
        lengths = tshark_frame_lengths(pcap, proto_filter)
        frame_count_port = len(lengths)
        if lengths:
            lengths.sort()
            avg_len = sum(lengths) / len(lengths)
            p95_len = percentile(lengths, 0.95)
            p99_len = percentile(lengths, 0.99)

    # Rates
    bytes_per_sec = None
    frames_per_sec = None
    if proto_stats and proto_stats.duration_s > 0:
        bytes_per_sec = proto_stats.bytes / proto_stats.duration_s
        frames_per_sec = proto_stats.frames / proto_stats.duration_s

    # Practical "frames per message": in port-based approach it's ~1
    # We keep it explicit but honest.
    frames_per_message = None
    if proto_stats and frame_count_port and frame_count_port > 0:
        # Here we treat "messages" as packets on that port; can be refined later
        frames_per_message = proto_stats.frames / frame_count_port

    scenario = pcap.stem  # filename without extension (good as unique id)

    return {
        "scenario": scenario,
        "pcap_path": str(pcap),
        "mode": meta["mode"],
        "proto": proto,
        "proto_port": proto_label,
        "N": meta["N"],
        "payload_size": meta["payload_size"],
        "duration_s_total": round(total.duration_s, 6),
        "frames_total": total.frames,
        "bytes_total": total.bytes,
        "duration_s_proto": round(proto_stats.duration_s, 6) if proto_stats else None,
        "frames_proto": proto_stats.frames if proto_stats else None,
        "bytes_proto": proto_stats.bytes if proto_stats else None,
        "avg_frame_len_proto": round(avg_len, 3) if avg_len is not None else None,
        "p95_frame_len_proto": round(p95_len, 3) if p95_len is not None else None,
        "p99_frame_len_proto": round(p99_len, 3) if p99_len is not None else None,
        "frames_per_sec_proto": round(frames_per_sec, 6) if frames_per_sec is not None else None,
        "bytes_per_sec_proto": round(bytes_per_sec, 6) if bytes_per_sec is not None else None,
        "frames_per_message_proxy": round(frames_per_message, 6) if frames_per_message is not None else None,
    }


def find_pcaps(root: Path) -> List[Path]:
    pcaps: List[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in PCAP_EXTS:
            pcaps.append(p)
    return sorted(pcaps)


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch PCAP metrics extractor -> CSV (for plots).")
    ap.add_argument("--root", required=True, help="Root directory containing results (will be scanned recursively).")
    ap.add_argument("--out", required=True, help="Output CSV path.")
    ap.add_argument("--append", action="store_true", help="Append to existing CSV (default overwrites header if empty).")
    args = ap.parse_args()

    require_tshark()

    root = Path(os.path.expanduser(args.root)).resolve()
    out_csv = Path(os.path.expanduser(args.out)).resolve()

    pcaps = find_pcaps(root)
    if not pcaps:
        print(f"ERROR: No .pcap/.pcapng found under: {root}", file=sys.stderr)
        sys.exit(1)

    fieldnames = [
        "scenario", "pcap_path", "mode", "proto", "proto_port", "N", "payload_size",
        "duration_s_total", "frames_total", "bytes_total",
        "duration_s_proto", "frames_proto", "bytes_proto",
        "avg_frame_len_proto", "p95_frame_len_proto", "p99_frame_len_proto",
        "frames_per_sec_proto", "bytes_per_sec_proto",
        "frames_per_message_proxy", "error",
    ]

    ensure_csv_header(out_csv, fieldnames)

    # If not append, we still keep header but we will rewrite rows from scratch
    rows: List[Dict[str, object]] = []

    for pcap in pcaps:
        try:
            row = compute_metrics_for_pcap(pcap)
            row["error"] = ""
            rows.append(row)
            print(f"[OK] {pcap}")
        except Exception as e:
            # zapisujemy minimalny wiersz + error
            meta = guess_meta_from_path(pcap)
            rows.append({
                "scenario": pcap.stem,
                "pcap_path": str(pcap),
                "mode": meta.get("mode"),
                "proto": meta.get("proto"),
                "proto_port": None,
                "N": meta.get("N"),
                "payload_size": meta.get("payload_size"),
                "duration_s_total": None,
                "frames_total": None,
                "bytes_total": None,
                "duration_s_proto": None,
                "frames_proto": None,
                "bytes_proto": None,
                "avg_frame_len_proto": None,
                "p95_frame_len_proto": None,
                "p99_frame_len_proto": None,
                "frames_per_sec_proto": None,
                "bytes_per_sec_proto": None,
                "frames_per_message_proxy": None,
                "error": str(e)[:200],
            })
            print(f"[FAIL] {pcap}: {e}", file=sys.stderr)

    # Write
    mode = "a" if args.append else "w"
    with out_csv.open(mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == "w":
            w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\nSaved CSV: {out_csv}")
    print(f"Rows written: {len(rows)} / PCAPs found: {len(pcaps)}")


if __name__ == "__main__":
    main()
