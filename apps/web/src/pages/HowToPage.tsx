import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { ListenButton } from "../guide/ListenButton";
import { useT } from "../lib/i18n";
import { useSession } from "../lib/sessionContext";
import { FACTORY_STEPS, TOUR_STEPS, VOICE_STEPS, WHY, openHowToPanel } from "../shell/HowToPanel";

/**
 * Instructions: what AaharOS is and why, then the two step-by-step routines every visitor follows (the guided tour,
 * then their own factory), and where the voice guide is. Each routine can be heard in English or Tamil.
 */
export function HowToPage() {
  const { t } = useT();
  const { me } = useSession();
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash]);
  return (
    <section className="admin-page howto-page">
      <h1>{t("Instructions")}</h1>
      <p className="lead">
        {t(
          "AaharOS runs a small snack factory from order to audit: salesmen take orders on the phone, the admin approves, invoices and dispatches, production records every batch and its cost, the owner sees where profit leaks, and the auditor downloads the month. Every number can be traced to the record it came from.",
        )}
      </p>
      <p>
        {t(
          "Everyone follows the same two routines: first the guided tour (on the shared DEMO factory), then your own factory. Both are below, step by step.",
        )}
      </p>
      <h2>{t("Why it is needed")}</h2>
      <ul className="howto-why">
        {WHY.map((s) => (
          <li key={s}>{t(s)}</li>
        ))}
      </ul>
      <p>
        <button type="button" className="btn" onClick={openHowToPanel}>
          {t("Keep these steps beside the screen")}
        </button>
      </p>

      <article className="howto-card" id="tour" aria-labelledby="tour-h">
        <header className="howto-card-head">
          <span className="howto-badge">1</span>
          <h2 id="tour-h">{t("Guided tour, step by step")}</h2>
          <ListenButton track="howto-tour" />
        </header>
        <ol className="howto-steps">
          {TOUR_STEPS.map((s) => (
            <li key={s}>{t(s)}</li>
          ))}
        </ol>
        <p className="actions-row">
          <Link to="/guide" className="btn btn-primary">
            {t("Start the guided tour →")}
          </Link>
        </p>
      </article>

      <article className="howto-card" id="own-factory" aria-labelledby="factory-h">
        <header className="howto-card-head">
          <span className="howto-badge">2</span>
          <h2 id="factory-h">{t("Your own factory, step by step")}</h2>
          <ListenButton track="howto-factory" />
        </header>
        <ol className="howto-steps">
          {FACTORY_STEPS.map((s) => (
            <li key={s}>{t(s)}</li>
          ))}
        </ol>
        <p className="actions-row">
          {me ? (
            <Link to="/owner" className="btn btn-primary">
              {t("Open my Morning brief →")}
            </Link>
          ) : (
            <Link to="/sign-up" className="btn btn-primary">
              {t("Create your own factory")}
            </Link>
          )}
        </p>
      </article>

      <article className="howto-card" id="voice" aria-labelledby="voice-h">
        <header className="howto-card-head">
          <span className="howto-badge" aria-hidden="true">
            🔊
          </span>
          <h2 id="voice-h">{t("Where is the voice guide?")}</h2>
        </header>
        <ol className="howto-steps">
          {VOICE_STEPS.map((s) => (
            <li key={s}>{t(s)}</li>
          ))}
        </ol>
        <p className="actions-row">
          <Link to="/guide" className="btn">
            {t("Open the tour with the voice guide →")}
          </Link>
        </p>
      </article>
    </section>
  );
}
