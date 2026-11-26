import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, apiGet, apiPost, refreshSession } from "./api";
import { SessionContext, type Me } from "./sessionContext";
import { authConfig, supabaseSignIn, supabaseSignOut, takePendingFactory } from "./supabaseAuth";

function isMe(value: unknown): value is Me {
  const m = value as Partial<Me> | null;
  return (
    !!m &&
    typeof m.role === "string" &&
    typeof m.user?.display_name === "string" &&
    !!m.organization
  );
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    // The access cookie lasts 15 minutes and /api/auth/* is never auto-refreshed, so on a 401 try the refresh cookie
    // (7 days) once before deciding the visitor is signed out.
    const whoAmI = () =>
      apiGet<Me>("/api/auth/me").catch(async (e: unknown) => {
        if (!(e instanceof ApiError) || e.status !== 401) throw e;
        if (!(await refreshSession())) throw e;
        return apiGet<Me>("/api/auth/me");
      });
    whoAmI()
      .then((m) => live && setMe(isMe(m) ? m : null))
      .catch(() => live && setMe(null))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string, organizationCode?: string) => {
    const cfg = await authConfig();
    let signedIn: Me;
    if (cfg.mode === "supabase") {
      // Supabase Auth checks the password; this app then opens its own session for the verified email
      const accessToken = await supabaseSignIn(cfg, email, password);
      const body: Record<string, string> = { access_token: accessToken };
      if (organizationCode) body.organization_code = organizationCode;
      try {
        signedIn = await apiPost<Me>("/api/auth/exchange", body);
      } catch (e) {
        // first sign-in after confirming the email: create the factory the visitor asked for, then sign in
        const pending =
          e instanceof ApiError && e.status === 401 ? takePendingFactory(email) : null;
        if (!pending) throw e;
        await apiPost("/api/signup", {
          factory_name: pending.factory_name,
          display_name: pending.display_name,
          access_token: accessToken,
        });
        signedIn = await apiPost<Me>("/api/auth/exchange", body);
      }
    } else {
      const body: Record<string, string> = { email, password };
      if (organizationCode) body.organization_code = organizationCode;
      signedIn = await apiPost<Me>("/api/auth/login", body);
    }
    setMe(signedIn);
    return signedIn;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiPost("/api/auth/logout");
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    const cfg = await authConfig();
    if (cfg.mode === "supabase") await supabaseSignOut(cfg); // end the Supabase session too
    setMe(null);
  }, []);

  const value = useMemo(() => ({ me, loading, signIn, signOut }), [me, loading, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
