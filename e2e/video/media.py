"""Demo video sound. `python media.py voice` records narration clips and their durations; `python media.py mux` lays
each clip at the time the recording reached that screen and writes an MP4 (H.264 + AAC). Needs edge-tts and ffmpeg."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
CLIPS = HERE / "clips"
VOICES = {"en": "en-IN-NeerjaNeural", "ta": "ta-IN-PallaviNeural"}


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


async def voice() -> None:
    import edge_tts

    CLIPS.mkdir(exist_ok=True)
    lines = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    durations = {}
    for key, (lang, text) in lines.items():
        target = CLIPS / f"{key}.mp3"
        await edge_tts.Communicate(text, VOICES[lang]).save(str(target))
        durations[key] = round(duration(target), 2)
    (HERE / "durations.json").write_text(json.dumps(durations, indent=1), encoding="utf-8")
    print(f"{len(durations)} clips, {sum(durations.values()):.0f} s of narration")


def mux() -> None:
    video = next((HERE / "out").glob("*.webm"))
    timeline = json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))
    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video)]
    parts = []
    for i, (key, ms) in enumerate(timeline, start=1):
        args += ["-i", str(CLIPS / f"{key}.mp3")]
        parts.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(1, len(timeline) + 1))
    graph = ";".join(parts) + f";{mix}amix=inputs={len(timeline)}:normalize=0[a]"
    out = HERE / "AaharOS-demo.mp4"
    args += ["-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "27", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
    subprocess.run(args, check=True)
    print(f"{out.name}: {duration(out):.0f} s, {out.stat().st_size // 1024 // 1024} MB")


if sys.argv[1] == "voice":
    asyncio.run(voice())
else:
    mux()
