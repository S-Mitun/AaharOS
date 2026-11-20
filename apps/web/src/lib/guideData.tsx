import { useEffect, useState, type ReactNode } from "react";
import { GuideDataContext } from "./guideStore";

/** Payload of GET /api/guide/expected: the oracle, every number as an exact string. */
export type OraclePayload = Record<string, unknown>;

export interface ScoreRow {
  n: number;
  title: string;
  owner_mp: string;
  status: "GREEN" | "RED" | "FAIL";
  detail: string;
  expected: Record<string, unknown>;
}

export type Scoreboard =
  | { available: false; reason: string }
  | { available: true; generated_at: string; green: number; total: number; rows: ScoreRow[] };

export type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ok"; data: T };

export interface GuideData {
  oracle: Load<OraclePayload>;
  scoreboard: Load<Scoreboard>;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return (await res.json()) as T;
}

function useLoad<T>(url: string): Load<T> {
  const [load, setLoad] = useState<Load<T>>({ state: "loading" });
  useEffect(() => {
    let alive = true;
    getJson<T>(url)
      .then((data) => alive && setLoad({ state: "ok", data }))
      .catch((e: unknown) => alive && setLoad({ state: "error", message: String(e) }));
    return () => {
      alive = false;
    };
  }, [url]);
  return load;
}

export function GuideDataProvider({ children }: { children: ReactNode }) {
  const oracle = useLoad<OraclePayload>("/api/guide/expected");
  const scoreboard = useLoad<Scoreboard>("/api/guide/scoreboard");
  return (
    <GuideDataContext.Provider value={{ oracle, scoreboard }}>{children}</GuideDataContext.Provider>
  );
}
