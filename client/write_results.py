# writeResults.py
import os

HEADER = "run_id,proto,client_id,ts,rtt,status,error\n"

def write_metric(csv_path: str, run_id: str, proto: str, client_id: str,
                 ts: float, rtt=None, status="", error="") -> None:
    """
    Minimalny zapis metryk do CSV.
    - csv_path: pełna ścieżka do pliku
    - rtt: float lub None
    """
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    new_file = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8") as f:
        if new_file:
            f.write(HEADER)

        rtt_str = "" if rtt is None else f"{rtt:.6f}"
        # error może zawierać przecinki/nowe linie -> proste "sanity"
        err = (error or "").replace("\n", " ").replace("\r", " ").replace(",", ";")
        f.write(f"{run_id},{proto},{client_id},{ts:.6f},{rtt_str},{status},{err}\n")
