import { createContext, useContext } from "react";

/** Who is signed in, as GET /api/auth/me describes it. */
export interface Me {
  user: { id: string; email: string; display_name: string };
  organization: { id: string; code: string; name: string; kind: string };
  role: string;
  permissions: string[];
}

export interface SessionState {
  me: Me | null;
  loading: boolean;
  signIn: (email: string, password: string, organizationCode?: string) => Promise<Me>;
  signOut: () => Promise<void>;
}

export const SessionContext = createContext<SessionState | null>(null);

export function useSession(): SessionState {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSession needs a SessionProvider");
  return s;
}
