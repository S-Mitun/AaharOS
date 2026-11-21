import { useRoutes } from "react-router-dom";
import { GuideDataProvider } from "./lib/guideData";
import { SessionProvider } from "./lib/session";
import { appRoutes } from "./routes";
import { OutboxProvider } from "./sales/outbox";

function Routes() {
  return useRoutes(appRoutes);
}

export function App() {
  return (
    <SessionProvider>
      <OutboxProvider>
        <GuideDataProvider>
          <Routes />
        </GuideDataProvider>
      </OutboxProvider>
    </SessionProvider>
  );
}
