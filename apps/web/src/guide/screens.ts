import type { Group, Screen } from "./types";

/**
 * The single registry of screens (MP08, G9). The sidebar, the routes and the tour's "Take me there" links all read
 * this, so they can never disagree. When an MP builds a screen it flips `built` to true; until then the route opens
 * an honest "Coming in MPxx" page that says what the screen will do, never sample numbers.
 */
export const SCREENS: Record<string, Screen> = {
  home: {
    name: "Start here",
    label: "Start here",
    route: "/",
    mp: "MP00",
    built: true,
    group: "Guide",
    icon: "⌂",
    description: "What AaharOS is, in one page.",
  },
  guide: {
    name: "Guided tour",
    label: "Guided tour",
    route: "/guide",
    mp: "MP00",
    built: true,
    group: "Guide",
    icon: "➜",
    description: "NIT's nine steps, one card each: who, where, what to type, what you should see.",
  },
  salesToday: {
    name: "Salesman app → Today",
    label: "Today",
    route: "/sales",
    mp: "MP08",
    built: true,
    group: "Salesman",
    icon: "☀",
    description: "Your customers in route order, with one-tap “Repeat last order”.",
    permission: "order.create",
  },
  salesOrder: {
    name: "Salesman app → New order",
    label: "New order",
    route: "/sales/order",
    mp: "MP08",
    built: true,
    group: "Salesman",
    icon: "＋",
    description: "Pick a customer, set packets, save. Works with no network.",
    permission: "order.create",
  },
  salesOrders: {
    name: "Salesman app → My orders",
    label: "My orders",
    route: "/sales/orders",
    mp: "MP08",
    built: true,
    group: "Salesman",
    icon: "☰",
    description: "Every order and where it is: saved on phone, received by factory, approved.",
    permission: "order.read",
  },
  salesSummary: {
    name: "Salesman app → Summary",
    label: "Summary",
    route: "/sales/summary",
    mp: "MP08",
    built: true,
    group: "Salesman",
    icon: "Σ",
    description: "Packets and order value per customer, last 30 days (ordered, not invoiced).",
    permission: "order.read",
  },
  orderInbox: {
    name: "Admin → Order inbox",
    label: "Order inbox",
    route: "/admin/orders",
    mp: "MP09",
    built: true,
    group: "Admin",
    icon: "✉",
    description: "Approve, part-approve or reject orders against available-to-promise stock.",
    permission: "order.approve",
  },
  invoices: {
    name: "Admin → Invoices and dispatch",
    label: "Invoices and dispatch",
    route: "/admin/invoices",
    mp: "MP10",
    built: true,
    group: "Admin",
    icon: "₹",
    description: "GST invoices (CGST + SGST or IGST) and FEFO dispatch, oldest batch first.",
    permission: "invoice.post",
  },
  collections: {
    name: "Admin → Collections",
    label: "Collections",
    route: "/admin/collections",
    mp: "MP10",
    built: true,
    group: "Admin",
    icon: "◎",
    description: "Record payments and see what each customer still owes.",
    permission: "payment.post",
  },
  purchases: {
    name: "Purchases → New receipt",
    label: "Purchases",
    route: "/admin/purchases/new",
    mp: "MP05",
    built: false,
    group: "Production",
    icon: "⇩",
    description:
      "Receive raw materials; the average cost updates itself. (The API is built; the screen is next.)",
    permission: "receipt.post",
  },
  batch: {
    name: "Production → Batch card",
    label: "Batch card",
    route: "/production/batch/new",
    mp: "MP06",
    built: false,
    group: "Production",
    icon: "⚙",
    description:
      "Start a batch, issue materials, record good packets and damage. (API built; screen next.)",
    permission: "run.start",
  },
  batchCosts: {
    name: "Batch → Run costs",
    label: "Run costs",
    route: "/production/batch",
    mp: "MP07",
    built: false,
    group: "Production",
    icon: "⏲",
    description: "Add labour and gas to a finished batch. (API built; screen next.)",
    permission: "run.cost",
  },
  morningBrief: {
    name: "Owner → Morning brief",
    label: "Morning brief",
    route: "/owner",
    mp: "MP12",
    built: true,
    group: "Owner",
    icon: "☼",
    description: "Five cards and today’s three actions, biggest rupee impact first.",
    permission: "report.read",
  },
  planner: {
    name: "Production → Batch planner",
    label: "Batch planner",
    route: "/production/planner",
    mp: "MP12",
    built: true,
    group: "Production",
    icon: "▦",
    description:
      "How many batches the stock allows, what to make next and what to buy. Creates drafts only.",
    permission: "report.read",
  },
  trace: {
    name: "Production → Trace and recall",
    label: "Trace and recall",
    route: "/production/trace",
    mp: "MP13",
    built: true,
    group: "Production",
    icon: "⇄",
    description:
      "Where a batch came from and where every packet went; simulate a recall (DEMO, nothing sent).",
    permission: "report.read",
  },
  profitLeaks: {
    name: "Where profit leaks",
    label: "Where profit leaks",
    route: "/leaks",
    mp: "MP07",
    built: true,
    group: "Owner",
    icon: "◔",
    description: "Each batch's cost against standard, as a waterfall. Tap ⓘ on any number.",
    permission: "report.read",
  },
  reports: {
    name: "Auditor → Reports",
    label: "Reports",
    route: "/auditor/reports",
    mp: "MP11",
    built: true,
    group: "Auditor",
    icon: "▤",
    description:
      "Registers, stock, production, ageing, GST, month-end close and the evidence pack.",
    permission: "report.read",
  },
  judge: {
    name: "Judge Mode",
    label: "Judge Mode",
    route: "/judge",
    mp: "MP15",
    built: false,
    group: "Judge",
    icon: "⚖",
    description:
      "Replay NIT's nine steps on a fresh factory and compare every figure with the oracle.",
  },
};

export function screenFor(id: string): Screen {
  const screen = SCREENS[id];
  if (!screen) throw new Error(`unknown screen id: ${id}`);
  return screen;
}

/** The group whose screens a role uses most, expanded after sign-in. */
export const ROLE_GROUP: Record<string, Group> = {
  SALESMAN: "Salesman",
  ADMIN: "Admin",
  PRODUCTION: "Production",
  OWNER: "Owner",
  AUDITOR: "Auditor",
};

/** Where each role lands after sign-in (G7). Roles whose shells come later land on today's pages. */
export function homeFor(role: string): string {
  if (role === "SALESMAN") return SCREENS.salesToday!.route;
  if (role === "ADMIN") return SCREENS.orderInbox!.route;
  if (role === "OWNER") return SCREENS.morningBrief!.route;
  if (role === "PRODUCTION") return SCREENS.planner!.route;
  return SCREENS.profitLeaks!.route;
}
