"""
Replay dataset events to the live ingest API at a configurable rate.

Usage examples:
  # Replay BGL at 20 events/sec (default)
  python scripts/replay_dataset.py --layer bgl

  # Replay CICIDS anomalies only at 5/sec, max 200 events
  python scripts/replay_dataset.py --layer cicids --rate 5 --max 200 --anomalies-only

  # Replay all layers at 50/sec
  python scripts/replay_dataset.py --layer all --rate 50 --max 1000

  # Replay at original timestamps scaled 100x faster
  python scripts/replay_dataset.py --layer bgl --time-mode scaled --speed 100
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_API  = "http://localhost:8000"
DEFAULT_RATE = 10          # events per second
DEFAULT_MAX  = 500         # max events to replay


def _get_db_url() -> str:
    """Load DATABASE_URL from backend .env."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "sqlite:///./crosslayer.db"


def _color(text: str, code: int) -> str:
    return f"\033[{code}m{text}\033[0m"


def red(t):    return _color(t, 31)
def green(t):  return _color(t, 32)
def yellow(t): return _color(t, 33)
def cyan(t):   return _color(t, 36)
def bold(t):   return _color(t, 1)


# ── Main replay logic ─────────────────────────────────────────────────────────

def replay(
    layer: str,
    rate: float,
    max_events: int,
    anomalies_only: bool,
    time_mode: str,   # "fixed" | "scaled"
    speed: float,
    api_base: str,
) -> None:
    db_url = _get_db_url()
    print(f"  DB  : {db_url[:60]}")
    print(f"  API : {api_base}")
    print(f"  Mode: {'anomalies only' if anomalies_only else 'all events'} | "
          f"layer={layer} | rate={rate}/s | max={max_events}")
    print()

    engine = create_engine(db_url, future=True, connect_args={"check_same_thread": False}
                           if "sqlite" in db_url else {})
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        from app.models.log_events import LogEvent

        query = db.query(LogEvent).order_by(LogEvent.timestamp)
        if layer != "all":
            query = query.filter(LogEvent.layer == layer)
        if anomalies_only:
            query = query.filter(LogEvent.label == 1)

        events = query.limit(max_events).all()

        if not events:
            print(red(f"  No events found for layer='{layer}'. Did you run Step 1 (ingest)?"))
            return

        print(f"  Replaying {bold(str(len(events)))} events…\n")

        sent = 0; anomalies = 0; errors = 0
        prev_ts = None
        sleep_fixed = 1.0 / max(rate, 0.01)

        for i, ev in enumerate(events):
            payload = {
                "layer":     ev.layer or "system",
                "source":    ev.source or ev.layer or "replay",
                "entity":    ev.entity,
                "message":   (ev.message or "")[:500],
                "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                "features":  ev.features or {},
                "raw":       (ev.raw or "")[:300],
            }

            try:
                resp = requests.post(
                    f"{api_base}/ingest/event",
                    json=payload,
                    timeout=5,
                )
                resp.raise_for_status()
                result = resp.json()
                sent += 1

                if result.get("anomaly"):
                    anomalies += 1
                    conf = result.get("confidence", 0)
                    print(
                        f"  {green('ANOMALY')}  [{ev.layer:12s}] "
                        f"entity={ev.entity or '—':20s}  "
                        f"conf={conf:.2f}  "
                        f"({sent}/{len(events)})"
                    )
                elif sent % 50 == 0:
                    print(f"  {cyan('.'*10)}  {sent}/{len(events)} sent  "
                          f"({anomalies} anomalies so far)")

            except requests.exceptions.ConnectionError:
                errors += 1
                if errors == 1:
                    print(red("  Cannot reach API. Is the backend running? (uvicorn app.main:app --reload)"))
                if errors > 3:
                    print(red("  Too many connection errors — aborting."))
                    break
                continue
            except Exception as exc:
                errors += 1
                print(yellow(f"  Event {i} error: {exc}"))

            # Sleep
            if time_mode == "scaled" and ev.timestamp and prev_ts is not None:
                delta = (ev.timestamp - prev_ts).total_seconds()
                wait  = max(0, delta / speed)
                if wait > 0.01:
                    time.sleep(wait)
            else:
                time.sleep(sleep_fixed)

            prev_ts = ev.timestamp

    finally:
        db.close()

    print()
    print(bold("  ── Summary ───────────────────────────────"))
    print(f"  Sent     : {sent}")
    print(f"  Anomalies: {anomalies}  ({100*anomalies/max(sent,1):.1f}%)")
    print(f"  Errors   : {errors}")
    print()
    if anomalies > 0:
        print(green("  Anomalies broadcast via WebSocket → check the dashboard!"))
    else:
        print(yellow("  No anomalies detected. Try --anomalies-only or train a model first."))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Replay dataset events to the CrossLayer ingest API in real time",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--layer",         default="bgl",    choices=["bgl", "cicids", "tda", "all"],
                   help="Dataset layer to replay (default: bgl)")
    p.add_argument("--rate",          type=float, default=DEFAULT_RATE,
                   help=f"Events per second in fixed mode (default: {DEFAULT_RATE})")
    p.add_argument("--max",           type=int,   default=DEFAULT_MAX,
                   help=f"Max events to replay (default: {DEFAULT_MAX})")
    p.add_argument("--anomalies-only", action="store_true",
                   help="Only replay events where label=1 (anomalies)")
    p.add_argument("--time-mode",     default="fixed", choices=["fixed", "scaled"],
                   help="fixed=constant rate, scaled=respect original timestamps (default: fixed)")
    p.add_argument("--speed",         type=float, default=100.0,
                   help="Speed multiplier for scaled mode — 100=100x faster than real time (default: 100)")
    p.add_argument("--api",           default=DEFAULT_API,
                   help=f"Backend API base URL (default: {DEFAULT_API})")

    args = p.parse_args()

    print()
    print(bold("  CrossLayer Dataset Replay Simulator"))
    print(bold("  ────────────────────────────────────"))

    replay(
        layer          = args.layer,
        rate           = args.rate,
        max_events     = args.max,
        anomalies_only = args.anomalies_only,
        time_mode      = args.time_mode,
        speed          = args.speed,
        api_base       = args.api,
    )


if __name__ == "__main__":
    main()
