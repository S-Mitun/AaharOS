import { SCREENS } from "../guide/screens";
import { GROUPS, type Group, type Screen } from "../guide/types";
import type { Me } from "../lib/sessionContext";

/** Screens a visitor or a role sees in the sidebar. Signed out: everything (to browse). Signed in: what the role
 * can use. The API enforces every permission regardless. */
export function visibleScreens(me: Me | null): Screen[] {
  return Object.values(SCREENS).filter(
    (s) => !s.hidden && (!me || !s.permission || me.permissions.includes(s.permission)),
  );
}

export function groupsFor(me: Me | null): { group: Group; screens: Screen[] }[] {
  const shown = visibleScreens(me);
  return GROUPS.map((group) => ({ group, screens: shown.filter((s) => s.group === group) })).filter(
    (g) => g.screens.length > 0,
  );
}
