"""Step 6: mix narration + ducked music + SFX, loudness-normalize, mux onto the rendered video."""
import json
import subprocess
from pathlib import Path


def mux(cfg, video: Path, voice: Path, music: Path, sfx: Path, dur: float, out: Path):
    a = cfg.audio
    mdb = float(a.get("music_db", -21))
    lufs = float(a.get("target_lufs", -14))
    fc = (
        f"[1:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v1][vkey];"
        f"[2:a]aresample=48000,aformat=channel_layouts=stereo,volume={mdb}dB,"
        f"afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 1.2):.2f}:d=1.2[m];"
        f"[m][vkey]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[mduck];"
        f"[3:a]aresample=48000,volume=-4dB[s];"
        f"[v1][mduck][s]amix=inputs=3:duration=first:normalize=0,"
        f"loudnorm=I={lufs}:TP=-1.0:LRA=9,atrim=0:{dur:.3f}[aout]"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video), "-i", str(voice), "-stream_loop", "-1", "-i", str(music), "-i", str(sfx),
        "-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)
