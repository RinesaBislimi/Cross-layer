import argparse
import csv
from pathlib import Path
from typing import Optional


def parse_bgl_line(line: str) -> Optional[dict]:
    """
    Parse one BGL log line.

    BGL.log format (space-separated):
      <alert_flag> <node_id> <date> <node_name> <datetime> <node_name2> <type> <level> <component> <message...>

    alert_flag:
      '-'          → normal event  (label = 0)
      anything else → anomaly type (label = 1)

    Example normal:
      - 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779 ... INFO ...

    Example anomaly:
      FATAL 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779 ... FATAL ...
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split()
    if len(parts) < 5:
        # Malformed line — store as-is with label 0
        return {
            "timestamp": "",
            "node_id": "",
            "log_message": line,
            "label": "0",
        }

    alert_flag = parts[0]            # '-' = normal; anything else = anomaly type
    label = "0" if alert_flag == "-" else "1"
    node_id = parts[1]
    # The embedded datetime is at index 4 (e.g. 2005-06-03-15.42.50.363779)
    timestamp = parts[4]
    # Message starts after node_name2 at index 5
    message = " ".join(parts[5:]) if len(parts) > 5 else ""

    return {
        "timestamp": timestamp,
        "node_id": node_id,
        "log_message": message,
        "label": label,
    }


def convert_log_to_csv(input_path: Path, output_path: Path) -> None:
    """
    Konverton një skedar BGL .log në një skedar CSV me kolonat:
    timestamp, node_id, log_message, label
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", errors="ignore") as fin, output_path.open(
        "w", newline="", encoding="utf-8"
    ) as fout:
        writer = csv.DictWriter(
            fout, fieldnames=["timestamp", "node_id", "log_message", "label"]
        )
        writer.writeheader()

        for line in fin:
            row = parse_bgl_line(line)
            if row is not None:
                writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert BGL .log file to CSV (timestamp,node_id,log_message,label)."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=False,
        default="data/bgl/BGL.log",
        help="Path i skedarit hyrës .log (default: data/bgl/BGL.log)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=False,
        default="data/bgl/bgl.csv",
        help="Path i skedarit dalës .csv (default: data/bgl/bgl.csv)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input .log file not found: {input_path}")

    convert_log_to_csv(input_path, output_path)
    print(f"Converted {input_path} -> {output_path}")


if __name__ == "__main__":
    main()

