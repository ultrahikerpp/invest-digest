"""
Combine image cards into a silent MP4 short video using FFmpeg.
Output format: 1080x1920, H.264, 30fps (suitable for YouTube Shorts / TikTok).
"""
import subprocess
import tempfile
from pathlib import Path


def _check_ffmpeg() -> None:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg not found.\n"
            "  macOS:  brew install ffmpeg\n"
            "  Linux:  apt-get install ffmpeg"
        )


def make_video(
    card_paths: list[Path],
    output_path: Path,
    seconds_per_card: int = 4,
) -> Path:
    """
    Create a silent MP4 from a list of PNG card images.

    Each card is displayed for `seconds_per_card` seconds.
    Output is 1080x1920 H.264 (9:16 vertical, YouTube Shorts / TikTok ready).
    """
    if not card_paths:
        raise ValueError("No card images provided.")

    _check_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build FFmpeg concat input file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for card in card_paths:
            f.write(f"file '{card.resolve()}'\n")
            f.write(f"duration {seconds_per_card}\n")
        # FFmpeg concat demuxer requires the last file listed twice (no duration on final entry)
        f.write(f"file '{card_paths[-1].resolve()}'\n")
        concat_file = Path(f.name)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        # Ensure output is exactly 1080x1920 (pad if source differs)
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0a0e1a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-800:]}")
    finally:
        concat_file.unlink(missing_ok=True)

    return output_path
