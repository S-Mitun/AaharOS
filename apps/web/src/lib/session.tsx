import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, apiGet, apiPost } from "./api";
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
    apiGet<Me>("/api/auth/me")
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
    setMe(await apiPost<Me>("/api/auth/login", body));
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
