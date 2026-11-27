"""Record the guided tour's voice: one MP3 per step per language, from scripts.json (the text each step card shows).

Run in a throwaway container (needs network):
  docker run --rm -v "$PWD:/w" -w /w python:3.12-slim sh -c "pip install -q edge-tts==7.3.1 && python scripts/tour-voice/make_audio.py"
Writes apps/web/public/voice/{en,ta}/{step}.mp3. Re-run whenever the tour text in steps.ts / stepsTa.ts changes.
"""

import asyncio
import json
import re
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "apps" / "web" / "public" / "voice"
VOICES = {"en": "en-IN-NeerjaNeural", "ta": "ta-IN-PallaviNeural"}


def spoken(text: str, lang: str) -> str:
    """Screen text made easier to listen to: symbols and units as words, no arrows or flags."""
    t = text.replace("⚑", "").replace(" , ", ", ").replace("·", ",").replace("“", "").replace("”", "")
    if lang == "ta":
        t = re.sub(r"₹\s?([\d,]+(?:\.\d+)?)", r"\1 ரூபாய்", t)
        t = re.sub(r"(\d)\s?kg\b", r"\1 கிலோ", t).replace("kg-க்கு", "கிலோவுக்கு")
        t = re.sub(r"(\d)\s?L\b", r"\1 லிட்டர்", t)
        t = re.sub(r"−\s?([\d.]+)%", r"மைனஸ் \1 சதவீதம்", t)
        t = re.sub(r"\+\s?([\d.]+)%", r"பிளஸ் \1 சதவீதம்", t)
        t = re.sub(r"([\d.]+)%", r"\1 சதவீதம்", t)
        t = t.replace("/ பாக்கெட்", "ஒரு பாக்கெட்டுக்கு").replace("/ kg", "ஒரு கிலோவுக்கு").replace("DEMO", "டெமோ")
    else:
        t = re.sub(r"₹\s?([\d,]+(?:\.\d+)?)\s?/\s?kg", r"\1 rupees per kg", t)
        t = re.sub(r"₹\s?([\d,]+(?:\.\d+)?)\s?/\s?packet", r"\1 rupees per packet", t)
        t = re.sub(r"₹\s?([\d,]+(?:\.\d+)?)", r"\1 rupees", t)
        t = re.sub(r"(\d)\s?L\b", r"\1 litres", t)
        t = t.replace("−", "minus ").replace("DEMO", "demo")
    return re.sub(r"\s+", " ", t).strip()


async def main() -> None:
    scripts = json.loads((Path(__file__).parent / "scripts.json").read_text(encoding="utf-8"))
    for lang, steps in scripts.items():
        (OUT / lang).mkdir(parents=True, exist_ok=True)
        for step, text in steps.items():
            target = OUT / lang / f"{step}.mp3"
            await edge_tts.Communicate(spoken(text, lang), VOICES[lang], rate="-5%").save(str(target))
            print(f"{lang}/{step}.mp3 {target.stat().st_size // 1024} KB")


asyncio.run(main())
