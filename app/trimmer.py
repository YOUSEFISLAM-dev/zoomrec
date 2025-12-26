"""
Auto-trim leading black frames from recordings.

Scans the top row of pixels and removes frames until non-black content appears.
Integrated into recording completion workflow.
"""

import os
import re
import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_first_nonblack_time(input_path: str) -> float:
    """
    Return the timestamp (seconds) where the top row of pixels stops being all black.
    Uses ffmpeg blackdetect filter on a 1px-high crop of the top row.
    """
    try:
        # Use lavfi input with movie filter to analyze top row only; escape quotes
        safe_path = str(input_path).replace("'", "\\'")
        filter_chain = f"movie='{safe_path}',crop=iw:1:0:0,blackdetect=d=0.05:pix_th=0.02"
        cmd = [
            "/usr/bin/ffmpeg",
            "-hide_banner",
            "-loglevel", "info",
            "-f", "lavfi",
            "-i", filter_chain,
            "-f", "null",
            "-",
        ]
        
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        stderr = proc.stderr
        
        # Find the last black_end timestamp (consecutive black segments)
        last_black_end = 0.0
        pattern = re.compile(r"black_end:([0-9]*\.?[0-9]+)")
        
        for line in stderr.splitlines():
            m = pattern.search(line)
            if m:
                try:
                    ts = float(m.group(1))
                    # Only consider if it's near the start (first 60s of black max)
                    if ts < 60.0:
                        last_black_end = ts
                except ValueError:
                    continue
        
        return last_black_end
        
    except subprocess.TimeoutExpired:
        logger.warning(f"Black detection timed out for {input_path}")
        return 0.0
    except Exception as e:
        logger.error(f"Black detection failed for {input_path}: {e}")
        return 0.0


def trim_video(input_path: str, output_path: str, start_time: float) -> bool:
    """
    Trim video from start_time using stream copy (fast, no re-encode).
    Returns True on success.
    """
    try:
        cmd = [
            "/usr/bin/ffmpeg",
            "-y",
            "-ss", f"{start_time:.3f}",
            "-i", input_path,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg trim failed: {result.stderr}")
            return False
            
        return os.path.exists(output_path)
        
    except subprocess.TimeoutExpired:
        logger.error(f"Trim timed out for {input_path}")
        return False
    except Exception as e:
        logger.error(f"Trim failed for {input_path}: {e}")
        return False


def auto_trim_recording(file_path: str, min_trim_seconds: float = 0.5) -> dict:
    """
    Auto-trim black frames from the start of a recording.
    
    Args:
        file_path: Path to the recording file
        min_trim_seconds: Minimum seconds of black to trigger trimming
        
    Returns:
        dict with keys:
            - trimmed: bool - whether trimming was performed
            - trim_seconds: float - seconds trimmed from start
            - output_path: str - path to final file (may be same as input if no trim)
            - error: str or None - error message if failed
    """
    result = {
        "trimmed": False,
        "trim_seconds": 0.0,
        "output_path": file_path,
        "error": None,
    }
    
    if not os.path.exists(file_path):
        result["error"] = "File not found"
        return result
    
    logger.info(f"Analyzing recording for black frames: {file_path}")
    
    # Find where black frames end
    trim_start = find_first_nonblack_time(file_path)
    result["trim_seconds"] = trim_start
    
    # Only trim if there's significant black content
    if trim_start < min_trim_seconds:
        logger.info(f"No significant black frames to trim ({trim_start:.2f}s)")
        return result
    
    logger.info(f"Found {trim_start:.2f}s of black frames to trim")
    
    # Create trimmed output
    path = Path(file_path)
    trimmed_path = path.parent / f"{path.stem}_trimmed{path.suffix}"
    
    if trim_video(file_path, str(trimmed_path), trim_start):
        # Replace original with trimmed version
        try:
            # Backup original just in case (optional - remove for prod)
            # backup_path = path.parent / f"{path.stem}_original{path.suffix}"
            # shutil.move(file_path, str(backup_path))
            
            # Replace original with trimmed
            os.remove(file_path)
            shutil.move(str(trimmed_path), file_path)
            
            result["trimmed"] = True
            result["output_path"] = file_path
            logger.info(f"Successfully trimmed {trim_start:.2f}s from recording")
            
        except Exception as e:
            result["error"] = f"Failed to replace file: {e}"
            logger.error(result["error"])
            # Clean up temp file
            if os.path.exists(str(trimmed_path)):
                os.remove(str(trimmed_path))
    else:
        result["error"] = "FFmpeg trim failed"
        # Clean up temp file if exists
        if os.path.exists(str(trimmed_path)):
            os.remove(str(trimmed_path))
    
    return result
