import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, apiGet, apiPost, refreshSession } from "./api";
import { SessionContext, type Me } from "./sessionContext";

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
    const body: Record<string, string> = { email, password };
    if (organizationCode) body.organization_code = organizationCode;
    const signedIn = await apiPost<Me>("/api/auth/login", body);
    setMe(signedIn);
    return signedIn;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiPost("/api/auth/logout");
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    setMe(null);
  }, []);

  const value = useMemo(() => ({ me, loading, signIn, signOut }), [me, loading, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
