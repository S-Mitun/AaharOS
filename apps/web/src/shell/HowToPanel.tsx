import { Link } from "react-router-dom";
import { useT } from "../lib/i18n";

/**
 * "How to": the two step-by-step recipes (the guided tour, and working in your own factory) in a panel that stays
 * open beside any screen, so a visitor can read a step and do it at the same time.
 */
export const TOUR_STEPS = [
  "Open the app and press Start the guided tour (or Restart tour in the top bar, at any time).",
  "Read the step card: who does it, where (Take me there opens the screen), what to do and what you should see.",
  "To hear it, press Listen to this step, or tick Read each step aloud. Press தமிழ் for Tamil text and a Tamil voice.",
  "Sign in as the person the card names: on the sign-in page one tap on a DEMO login fills it in.",
  "Do the step on the screen and compare your numbers with What you should see. Tap ⓘ on any number to see where it came from.",
  "Press the Guide button (bottom right) to come back to the same step, then press Next.",
  "Repeat for all 12 steps. On the last step press Finish the tour.",
  "Choose Create your own factory, or Sign in to my account.",
];

export const FACTORY_STEPS = [
  "Finish the guided tour on this device: creating a factory opens only after the tour.",
  "Press Create your own factory (on the finish panel, the home page or the sign-in page).",
  "Enter a factory name, your name, your email and a password of at least 10 characters, then press Create my factory.",
  "You are signed in as the Owner of a private factory with the same opening stock, recipe, customers and prices as the tour.",
  "Work through a day in the menu: Purchases → Batch card → Today (orders) → Order inbox → Invoices and dispatch → Collections → Run costs → Morning brief → Reports.",
  "Change thresholds, prices or GST rates in Owner → Settings; a change applies from the date you pick.",
  "Sign out from the top bar. Next time, sign in with the same email and password to continue where you left off.",
  "Press Restart tour at any time to go over a step again.",
];

export const VOICE_STEPS = [
  "Open the Guided tour (menu → Guide → Guided tour, or Start the guided tour on the home page).",
  "Above every step card is the voice bar: press 🔊 Listen to this step to hear it, Pause or Stop at any time.",
  "Tick Read each step aloud and every step is read as you move with Next.",
  "Press தமிழ் in the top bar: the text and the voice change to Tamil at once. Press English to go back.",
  "On this Instructions page, 🔊 Listen reads each routine aloud as well.",
];

export const WHY = [
  "Stock is never guessed: every gram moves through a double-entry stock ledger and can never go below zero.",
  "Cost is explained: each batch's cost per good packet comes from real material, labour and gas, and the gap against standard is shown step by step.",
  "Tax is consistent: invoice tax lines, the GST summary and the GSTR-1 file are the same numbers.",
  "Every number can be checked: tap ⓘ beside any figure to see its formula and source record.",
  "People are not slowed down: orders work offline on a phone, approval is one tap, month end is a download.",
];

const EVENT = "aaharos:howto-panel";
/** Open the steps panel beside the current screen (the shell listens). */
export function openHowToPanel() {
  window.dispatchEvent(new Event(EVENT));
}
export function onOpenHowToPanel(handler: () => void): () => void {
  window.addEventListener(EVENT, handler);
  return () => window.removeEventListener(EVENT, handler);
}

export function HowToPanel({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  return (
    <aside className="howto" aria-labelledby="howto-h">
      <div className="howto-head">
        <h2 id="howto-h">{t("How to use AaharOS")}</h2>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={onClose}
          aria-label={t("Close the steps")}
        >
          ✕
        </button>
      </div>
      <p className="muted small">{t("Keep this panel open and work on the screen beside it.")}</p>
      <p>
        <Link to="/how-to" className="link-strong">
          {t("Open the full instructions →")}
        </Link>
      </p>
      <h3>{t("Guided tour, step by step")}</h3>
      <ol>
        {TOUR_STEPS.map((s) => (
          <li key={s}>{t(s)}</li>
        ))}
      </ol>
      <h3>{t("Your own factory, step by step")}</h3>
      <ol>
        {FACTORY_STEPS.map((s) => (
          <li key={s}>{t(s)}</li>
        ))}
      </ol>
    </aside>
  );
}
