import ffmpeg
import subprocess
import os
import tempfile


def get_audio_duration_ffmpeg(file_path: str) -> float:
    try:
        probe = ffmpeg.probe(file_path)
        if 'format' in probe and 'duration' in probe['format']:
            return float(probe['format']['duration'])
        audio_stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'audio'), None)
        if audio_stream and 'duration' in audio_stream:
            return float(audio_stream['duration'])
    except ffmpeg.Error:
        pass
    except Exception:
        pass
    return 0.0


def get_metadata(file_path: str) -> dict:
    try:
        probe = ffmpeg.probe(file_path)
        return probe.get('format', {}).get('tags', {}) or {}
    except Exception:
        return {}


def extract_cover_art(file_path: str, out_dir: str = None) -> str | None:
    if out_dir is None:
        out_dir = tempfile.gettempdir()

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    jpg_out = os.path.join(out_dir, f"{base_name}_cover.jpg")
    png_out = os.path.join(out_dir, f"{base_name}_cover.png")

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", file_path,
        "-map", "0:v:0",
        "-c", "copy",
        jpg_out
    ]
    try:
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc.returncode == 0 and os.path.exists(jpg_out) and os.path.getsize(jpg_out) > 0:
            return jpg_out
    except Exception:
        pass

    try:
        cmd2 = [
            "ffmpeg", "-y", "-v", "error", "-i", file_path,
            "-an", "-vcodec", "copy", jpg_out
        ]
        rc = subprocess.run(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc.returncode == 0 and os.path.exists(jpg_out) and os.path.getsize(jpg_out) > 0:
            return jpg_out
    except Exception:
        pass

    try:
        cmd3 = [
            "ffmpeg", "-y", "-v", "error", "-i", file_path,
            "-map", "0:v:0",
            "-c", "copy",
            png_out
        ]
        rc = subprocess.run(cmd3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc.returncode == 0 and os.path.exists(png_out) and os.path.getsize(png_out) > 0:
            return png_out
    except Exception:
        pass

    return None


def _start_ffplay_at(file_path: str, start_seconds: float) -> subprocess.Popen:
    ss_args = []
    if start_seconds and start_seconds > 0:
        ss_args = ["-ss", str(float(start_seconds))]

    cmd = ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "error"] + ss_args + [file_path]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


def play(audio_file: str, ts: float):
    proc = _start_ffplay_at(audio_file, ts)
    return (proc,)

