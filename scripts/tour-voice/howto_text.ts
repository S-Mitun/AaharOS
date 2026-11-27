// Writes the spoken text of the Instructions page routines into scripts.json. Run with vite-node from apps/web (needs its node_modules), then: python scripts/tour-voice/make_audio.py howto-tour howto-factory
import { readFileSync, writeFileSync } from "node:fs";
import { TA } from "../../apps/web/src/lib/ta";
import { FACTORY_STEPS, TOUR_STEPS } from "../../apps/web/src/shell/HowToPanel";

const file = "/workspace/scripts/tour-voice/scripts.json";
const scripts = JSON.parse(readFileSync(file, "utf8"));
const say = (title: string, steps: string[], lang: "en" | "ta") => {
  const tr = (s: string) => (lang === "ta" ? (TA[s] ?? s) : s);
  const num = (i: number) => (lang === "ta" ? `படி ${i + 1}.` : `Step ${i + 1}.`);
  return [tr(title) + ".", ...steps.map((s, i) => `${num(i)} ${tr(s)}`)].join(" ");
};
for (const lang of ["en", "ta"] as const) {
  scripts[lang]["howto-tour"] = say("Guided tour, step by step", TOUR_STEPS, lang);
  scripts[lang]["howto-factory"] = say("Your own factory, step by step", FACTORY_STEPS, lang);
}
writeFileSync(file, JSON.stringify(scripts, null, 0), "utf8");
console.log(scripts.ta["howto-factory"].slice(0, 160));
