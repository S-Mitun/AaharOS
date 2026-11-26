import { useRoutes } from "react-router-dom";
import { GuideDataProvider } from "./lib/guideData";
import { LanguageProvider } from "./lib/i18n";
import { SessionProvider } from "./lib/session";
import { appRoutes } from "./routes";
import { OutboxProvider } from "./sales/outbox";

function Routes() {
  return useRoutes(appRoutes);
}

export function App() {
  return (
    <LanguageProvider>
      <SessionProvider>
        <OutboxProvider>
          <GuideDataProvider>
            <Routes />
          </GuideDataProvider>
        </OutboxProvider>
      </SessionProvider>
    </LanguageProvider>
  );
}
