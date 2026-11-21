import type { Screen } from "./types";

/**
 * Every screen the guide can point to. When an MP builds a screen it flips `built` to true,
 * and the guide's "Take me there" link starts working. Unbuilt screens are shown as "Coming in MPxx".
 */
export const SCREENS: Record<string, Screen> = {
  home: { name: "Start here", route: "/", mp: "MP00", built: true },
  guide: { name: "Guided tour", route: "/guide", mp: "MP00", built: true },
  purchases: {
    name: "Purchases → New receipt",
    route: "/admin/purchases/new",
    mp: "MP05",
    built: false,
  },
  batch: {
    name: "Production → Batch card",
    route: "/production/batch/new",
    mp: "MP06",
    built: false,
  },
  batchCosts: { name: "Batch → Run costs", route: "/production/batch", mp: "MP07", built: false },
  profitLeaks: {
    name: "Where profit leaks",
    route: "/leaks",
    mp: "MP07",
    built: true,
  },
  salesOrder: { name: "Salesman app → New order", route: "/sales/order", mp: "MP08", built: false },
  orderInbox: { name: "Admin → Order inbox", route: "/admin/orders", mp: "MP09", built: false },
  invoices: {
    name: "Admin → Invoices and dispatch",
    route: "/admin/invoices",
    mp: "MP10",
    built: false,
  },
  collections: {
    name: "Admin → Collections",
    route: "/admin/collections",
    mp: "MP10",
    built: false,
  },
  reports: { name: "Auditor → Reports", route: "/auditor/reports", mp: "MP11", built: false },
  judge: { name: "Judge Mode", route: "/judge", mp: "MP15", built: false },
};

export function screenFor(id: string): Screen {
  const screen = SCREENS[id];
  if (!screen) throw new Error(`unknown screen id: ${id}`);
  return screen;
}
