import { useT } from "../lib/i18n";
import { NavLink, useLocation } from "react-router-dom";
import { ROLE_GROUP } from "../guide/screens";
import type { Me } from "../lib/sessionContext";
import { groupsFor } from "./nav";

export function Sidebar({ me, onNavigate }: { me: Me | null; onNavigate?: () => void }) {
  const { pathname } = useLocation();
  const { t } = useT();
  const roleGroup = me ? ROLE_GROUP[me.role] : undefined;
  return (
    <nav aria-label="All screens" className="sidebar-nav">
      {groupsFor(me).map(({ group, screens }) => {
        const holdsCurrent = screens.some((s) =>
          s.route === "/" ? pathname === "/" : pathname.startsWith(s.route),
        );
        const open = !me || group === "Guide" || group === roleGroup || holdsCurrent;
        return (
          <details key={group} className="side-group" open={open}>
            <summary>
              {t(group)}
              {roleGroup === group && <span className="side-you">{t("you")}</span>}
            </summary>
            <ul>
              {screens.map((s) => (
                <li key={s.route}>
                  <NavLink
                    to={s.route}
                    end={s.route === "/" || s.route === "/sales"}
                    onClick={onNavigate}
                    className="side-link"
                    title={s.description}
                  >
                    <span className="side-icon" aria-hidden="true">
                      {s.icon}
                    </span>
                    <span className="side-label">{t(s.label)}</span>
                    {!s.built && <span className="side-soon">{s.mp}</span>}
                  </NavLink>
                </li>
              ))}
            </ul>
          </details>
        );
      })}
    </nav>
  );
}
