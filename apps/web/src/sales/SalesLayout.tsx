import { Outlet } from "react-router-dom";
import { Gate } from "../shell/Gate";
import { SalesTabs } from "./ui";

/** The salesman area (mobile-first): tabs, the connection banner and the page. */
export function SalesLayout() {
  return (
    <Gate permission="order.read" what="the salesman app">
      <div className="sales-area">
        <SalesTabs />
        <Outlet />
      </div>
    </Gate>
  );
}
