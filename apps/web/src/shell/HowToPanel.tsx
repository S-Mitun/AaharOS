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
