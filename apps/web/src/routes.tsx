/* eslint-disable react-refresh/only-export-components -- a route table, not a hot-reloaded component module */
import type { ReactNode } from "react";
import type { RouteObject } from "react-router-dom";
import { SCREENS } from "./guide/screens";
import { GuidePage } from "./pages/GuidePage";
import { CollectionsPage } from "./admin/CollectionsPage";
import { InboxPage } from "./admin/InboxPage";
import { InvoicePage } from "./admin/InvoicePage";
import { InvoicesPage } from "./admin/InvoicesPage";
import { OrderCardPage } from "./admin/OrderCardPage";
import { HomePage } from "./pages/HomePage";
import { ReportsPage } from "./reports/ReportsPage";
import { LeaksIndexPage, LeaksPage } from "./pages/LeaksPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { BriefPage } from "./owner/BriefPage";
import { PlannerPage } from "./owner/PlannerPage";
import { SignInPage } from "./pages/SignInPage";
import { MyOrdersPage } from "./sales/MyOrdersPage";
import { OrderDetailPage } from "./sales/OrderDetailPage";
import { OrderPage } from "./sales/OrderPage";
import { SalesLayout } from "./sales/SalesLayout";
import { SummaryPage } from "./sales/SummaryPage";
import { TodayPage } from "./sales/TodayPage";
import { AppShell } from "./shell/AppShell";
import { ComingPage } from "./shell/ComingPage";
import { Gate } from "./shell/Gate";

/** The page of every built screen in the registry (screens.ts). A screen not built yet gets the "Coming" page. */
const BUILT: Record<string, ReactNode> = {
  home: <HomePage />,
  guide: <GuidePage />,
  profitLeaks: <LeaksIndexPage />,
  orderInbox: (
    <Gate permission="order.approve" what="the order inbox">
      <InboxPage />
    </Gate>
  ),
  invoices: (
    <Gate permission="invoice.post" what="invoices and dispatch">
      <InvoicesPage />
    </Gate>
  ),
  reports: (
    <Gate permission="report.read" what="reports">
      <ReportsPage />
    </Gate>
  ),
  collections: (
    <Gate permission="payment.post" what="collections">
      <CollectionsPage />
    </Gate>
  ),
  morningBrief: (
    <Gate permission="report.read" what="the morning brief">
      <BriefPage />
    </Gate>
  ),
  planner: (
    <Gate permission="report.read" what="the batch planner">
      <PlannerPage />
    </Gate>
  ),
};

const SALES_ROUTES = new Set(["salesToday", "salesOrder", "salesOrders", "salesSummary"]);

function screenRoutes(): RouteObject[] {
  return Object.entries(SCREENS)
    .filter(([id]) => !SALES_ROUTES.has(id))
    .map(([id, screen]) => ({
      path: screen.route,
      element: screen.built ? BUILT[id] : <ComingPage screen={screen} />,
    }));
}

/** One app, one route table: the registry's screens plus the pages they lead to. */
export const appRoutes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      ...screenRoutes(),
      { path: "/guide/:stepId", element: <GuidePage /> },
      { path: "/leaks/:runId", element: <LeaksPage /> },
      { path: "/sign-in", element: <SignInPage /> },
      {
        path: "/admin/invoices/:invoiceId",
        element: (
          <Gate permission="report.read" what="this invoice">
            <InvoicePage />
          </Gate>
        ),
      },
      {
        path: "/admin/orders/:orderId",
        element: (
          <Gate permission="order.approve" what="the order inbox">
            <OrderCardPage />
          </Gate>
        ),
      },
      {
        path: "/sales",
        element: <SalesLayout />,
        children: [
          { index: true, element: <TodayPage /> },
          { path: "order", element: <TodayPage picking /> },
          { path: "order/:customerId", element: <OrderPage /> },
          { path: "orders", element: <MyOrdersPage /> },
          { path: "orders/:orderId", element: <OrderDetailPage /> },
          { path: "summary", element: <SummaryPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
