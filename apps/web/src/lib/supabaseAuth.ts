import { ApiError, apiGet } from "./api";

/**
 * Sign-in with Supabase Auth (hosted mode). The browser talks to Supabase's own endpoints (its OAuth 2 password grant,
 * sign-up and logout); the app server then checks the Supabase token once (`POST /api/auth/exchange`) and opens its
 * own httpOnly-cookie session. The Supabase access token is kept for this tab only, to sign out properly at Supabase.
 */
export interface AuthConfig {
  mode: "local" | "supabase";
  supabase_url?: string;
  supabase_key?: string;
}

const TOKEN_KEY = "aaharos.supabase.token";
let cached: Promise<AuthConfig> | null = null;

export function authConfig(): Promise<AuthConfig> {
  cached ??= apiGet<AuthConfig>("/api/auth/config").catch(() => ({ mode: "local" }) as AuthConfig);
  return cached;
}

async function call(cfg: AuthConfig, path: string, body?: unknown, token?: string) {
  const res = await fetch(`${cfg.supabase_url}/auth/v1/${path}`, {
    method: "POST",
    headers: {
      apikey: cfg.supabase_key ?? "",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = (await res.json().catch(() => ({}))) as {
    access_token?: string;
    error_code?: string;
    msg?: string;
    error_description?: string;
  };
  return { ok: res.ok, status: res.status, data };
}

function remember(token: string) {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage blocked: sign-out still ends the app session */
  }
}

export async function supabaseSignIn(
  cfg: AuthConfig,
  email: string,
  password: string,
): Promise<string> {
  const r = await call(cfg, "token?grant_type=password", { email, password });
  if (!r.ok || !r.data.access_token) {
    const unconfirmed = r.data.error_code === "email_not_confirmed";
    throw new ApiError(
      r.status,
      r.data.error_code ?? "sign_in_failed",
      unconfirmed ? "Confirm your email address first." : "Wrong email or password.",
    );
  }
  remember(r.data.access_token);
  return r.data.access_token;
}

/** Create the account at Supabase (or sign in if it already exists there) and return its access token. */
export async function supabaseSignUp(
  cfg: AuthConfig,
  email: string,
  password: string,
): Promise<string> {
  const r = await call(cfg, "signup", { email, password });
  if (r.ok && r.data.access_token) {
    remember(r.data.access_token);
    return r.data.access_token;
  }
  if (r.data.error_code === "user_already_exists") return supabaseSignIn(cfg, email, password);
  if (r.ok)
    throw new ApiError(
      400,
      "email_not_confirmed",
      "Check your inbox and confirm the email, then sign in here: your factory is created at that first sign-in.",
    );
  throw new ApiError(
    r.status,
    r.data.error_code ?? "sign_up_failed",
    r.data.msg ?? "Could not create the account.",
  );
}

export async function supabaseSignOut(cfg: AuthConfig): Promise<void> {
  let token: string | null = null;
  try {
    token = sessionStorage.getItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* nothing stored */
  }
  if (token) await call(cfg, "logout", undefined, token).catch(() => undefined);
}

/**
 * A sign-up that waits for the email to be confirmed (when Supabase asks for that): the factory's name is kept on this
 * device and the factory is created at the first sign-in after confirming.
 */
const PENDING_KEY = "aaharos.pending.factory";
export interface PendingFactory {
  email: string;
  factory_name: string;
  display_name: string;
}

export function savePendingFactory(p: PendingFactory) {
  try {
    localStorage.setItem(PENDING_KEY, JSON.stringify({ ...p, email: p.email.toLowerCase() }));
  } catch {
    /* storage blocked: the visitor signs up again after confirming */
  }
}

export function takePendingFactory(email: string): PendingFactory | null {
  try {
    const p = JSON.parse(localStorage.getItem(PENDING_KEY) ?? "null") as PendingFactory | null;
    if (!p || p.email !== email.toLowerCase()) return null;
    localStorage.removeItem(PENDING_KEY);
    return p;
  } catch {
    return null;
  }
}
