#!/usr/bin/env python3
"""
Trim leading black frames by inspecting only the first row of the video.

Logic:
- Use ffmpeg+blackdetect on a 1px-high crop of the top row to find the last black_end timestamp.
- Trim the source from that timestamp onward, copying streams to avoid re-encode.

Usage:
  python scripts/trim_black_head.py input.mp4 output.mp4
"""
import re
import subprocess
import sys
from pathlib import Path

def find_first_nonblack_time(input_path: Path) -> float:
    """Return the timestamp (seconds) where the top row stops being all black."""
    filter_chain = f"movie={input_path},crop=iw:1:0:0,blackdetect=d=0.05:pix_th=0.0"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-f",
        "lavfi",
        "-i",
        filter_chain,
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr = proc.stderr
    last_black_end = 0.0
    pattern = re.compile(r"black_end:([0-9]*\.?[0-9]+)")
    for line in stderr.splitlines():
        m = pattern.search(line)
        if m:
            try:
                last_black_end = float(m.group(1))
            except ValueError:
                continue
    return last_black_end


def trim_video(input_path: Path, output_path: Path, start_time: float) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_time:.3f}",
        "-i",
        str(input_path),
        "-c",
        "copy",
        str(output_path),
    ]
    subprocess.check_call(cmd)


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/trim_black_head.py input.mp4 output.mp4")
        sys.exit(1)

    input_path = Path(sys.argv[1]).expanduser().resolve()
    output_path = Path(sys.argv[2]).expanduser().resolve()

    if not input_path.exists():
        print(f"Input not found: {input_path}")
        sys.exit(1)

    trim_start = find_first_nonblack_time(input_path)
    print(f"Trimming from {trim_start:.3f}s")
    trim_video(input_path, output_path, trim_start)
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
