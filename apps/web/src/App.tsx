import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { GuideDataProvider } from "./lib/guideData";
import { SessionProvider } from "./lib/session";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { LeaksIndexPage, LeaksPage } from "./pages/LeaksPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SignInPage } from "./pages/SignInPage";

export function App() {
  return (
    <SessionProvider>
      <GuideDataProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="guide" element={<GuidePage />} />
            <Route path="guide/:stepId" element={<GuidePage />} />
            <Route path="sign-in" element={<SignInPage />} />
            <Route path="leaks" element={<LeaksIndexPage />} />
            <Route path="leaks/:runId" element={<LeaksPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </GuideDataProvider>
    </SessionProvider>
  );
}
