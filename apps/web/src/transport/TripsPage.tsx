import { useCallback, useEffect, useState } from "react";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import type { Explained } from "../lib/explained";
import { useSession } from "../lib/sessionContext";

interface PlanStop {
  seq: number;
  dispatch_no: string;
  invoice_no: string;
  customer: string;
  packets: string;
  cartons: string;
  leg_km: string;
  cost_share: string;
}
interface PlanRoute {
  vehicle: string;
  capacity_cartons: number;
  cartons: number;
  km: string;
  cost: Explained;
  co2: Explained;
  stops: PlanStop[];
  return_km: string;
  backhaul: { supplier: string; detour_km: string; text: string }[];
}
interface Plan {
  date: string;
  routing: string;
  routes: PlanRoute[];
  unplanned: { dispatch_no: string; customer: string | null; reason: string }[];
  note: string;
}
interface TripRow {
  id: string;
  trip_no: string;
  trip_date: string;
  status: "PLANNED" | "DONE";
  vehicle: string;
  planned_km: string | null;
  actual_km: string | null;
  planned_cost: Explained;
  actual_cost: Explained | null;
  co2: Explained;
  stops: { seq: number; customer: string; packets: string; cost_share: string }[];
}
interface ServeRow {
  customer_id: string;
  customer_name: string;
  packets: string;
  delivery: Explained;
  credit: Explained;
  returns: Explained;
  total: Explained;
  per_packet: Explained | null;
  price_floor: Explained | null;
}

/** Today's date where the browser is (the factory's day), as YYYY-MM-DD. */
const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

/**
 * Admin → Trips and cost-to-serve (MP14, ADR-0021): plan the day's delivery trips from its dispatch notes, record
 * actual km and tolls, and see what serving each customer costs with a Deal Desk price floor. Management figures:
 * nothing here posts to the books. Distances are straight-line x a road factor (no map service).
 */
export function TripsPage() {
  const { me } = useSession();
  const canDispatch = !!me?.permissions.includes("dispatch.post");
  const [day, setDay] = useState(today());
  const [plan, setPlan] = useState<Plan | null>(null);
  const [trips, setTrips] = useState<TripRow[]>([]);
  const [serve, setServe] = useState<ServeRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [actual, setActual] = useState<Record<string, { km: string; tolls: string }>>({});

  const load = useCallback(() => {
    apiGet<Plan>(`/api/transport/plan?on=${day}`)
      .then((p) => {
        setPlan(p);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not plan the trips."));
    apiGet<{ trips: TripRow[] }>("/api/transport/trips")
      .then((t) => setTrips(t.trips))
      .catch(() => undefined);
    apiGet<{ rows: ServeRow[] }>("/api/transport/cost-to-serve?days=30")
      .then((c) => setServe(c.rows))
      .catch(() => undefined);
  }, [day]);
  useEffect(load, [load]);

  async function act(what: () => Promise<string>) {
    setError(null);
    setDone(null);
    try {
      setDone(await what());
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
    }
  }

  return (
    <section className="admin-page trips">
      <h1>Trips and cost-to-serve</h1>
      <p className="muted">
        Plan delivery trips from a day&apos;s dispatch notes, record what was actually driven, and
        see what serving each customer costs. Management figures only: nothing is posted.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {done && (
        <p className="done" role="status">
          {done}
        </p>
      )}

      <h2>Plan a day</h2>
      <div className="trace-search">
        <label>
          Dispatch date
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </label>
        {canDispatch && plan && plan.routes.length > 0 && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              void act(async () => {
                const r = await apiPost<{ trips: string[] }>("/api/transport/trips", { on: day });
                return `Trips ${r.trips.join(", ")} created. Record the actual km when they return.`;
              })
            }
          >
            Create these trips
          </button>
        )}
      </div>
      {plan && (
        <>
          <p className="muted small">
            {plan.note} Routing: {plan.routing}.
          </p>
          {plan.routes.length === 0 && plan.unplanned.length === 0 && (
            <p className="muted">No dispatch note of {plan.date} is waiting for a trip.</p>
          )}
          {plan.routes.map((r) => (
            <div key={r.vehicle} className="table-wrap">
              <p>
                <strong>{r.vehicle}</strong> · {r.cartons} of {r.capacity_cartons} cartons · {r.km}{" "}
                km · <Num value={r.cost} label={`planned cost of the ${r.vehicle} trip`} /> ·{" "}
                <Num value={r.co2} label={`estimated CO2 of the ${r.vehicle} trip`} />
              </p>
              <ol className="trip-stops">
                {r.stops.map((s) => (
                  <li key={s.dispatch_no}>
                    {s.customer} · {s.dispatch_no} ({s.invoice_no}) · {s.packets} packets ·{" "}
                    {s.leg_km} km from the last stop · share ₹{s.cost_share}
                  </li>
                ))}
              </ol>
              <p className="muted small">Back to the factory: {r.return_km} km.</p>
              {r.backhaul.map((b) => (
                <p key={b.supplier}>
                  <StatusChip tone="info">backhaul</StatusChip> {b.text}
                </p>
              ))}
            </div>
          ))}
          {plan.unplanned.map((u) => (
            <p key={u.dispatch_no}>
              <StatusChip tone="warn">not planned</StatusChip> {u.dispatch_no} ({u.customer}):{" "}
              {u.reason}
            </p>
          ))}
        </>
      )}

      <h2>Trips (last 30 days)</h2>
      {trips.length === 0 ? (
        <p className="muted">No trips yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="lines">
            <thead>
              <tr>
                <th>Trip</th>
                <th>Stops</th>
                <th className="num">Planned</th>
                <th className="num">Actual</th>
                <th className="num">CO2</th>
              </tr>
            </thead>
            <tbody>
              {trips.map((t) => (
                <tr key={t.id}>
                  <td>
                    <strong>{t.trip_no}</strong>{" "}
                    <span className="muted small">
                      {t.trip_date} · {t.vehicle}
                    </span>{" "}
                    {t.status === "DONE" ? (
                      <StatusChip tone="ok">done</StatusChip>
                    ) : (
                      <StatusChip tone="todo">planned</StatusChip>
                    )}
                  </td>
                  <td>{t.stops.map((s) => `${s.customer} (${s.packets})`).join(" → ")}</td>
                  <td className="num">
                    {t.planned_km} km ·{" "}
                    <Num value={t.planned_cost} label={`planned cost of ${t.trip_no}`} />
                  </td>
                  <td className="num">
                    {t.actual_cost ? (
                      <>
                        {t.actual_km} km ·{" "}
                        <Num value={t.actual_cost} label={`actual cost of ${t.trip_no}`} />
                      </>
                    ) : canDispatch ? (
                      <form
                        className="actual-form"
                        onSubmit={(e) => {
                          e.preventDefault();
                          const a = actual[t.id] ?? { km: "", tolls: "0" };
                          void act(async () => {
                            await apiPost(`/api/transport/trips/${t.id}/complete`, {
                              actual_km: a.km,
                              tolls: a.tolls || "0",
                            });
                            return `${t.trip_no} recorded.`;
                          });
                        }}
                      >
                        <input
                          aria-label={`actual km of ${t.trip_no}`}
                          inputMode="decimal"
                          placeholder="km"
                          required
                          value={actual[t.id]?.km ?? ""}
                          onChange={(e) =>
                            setActual({
                              ...actual,
                              [t.id]: { km: e.target.value, tolls: actual[t.id]?.tolls ?? "0" },
                            })
                          }
                        />
                        <input
                          aria-label={`tolls of ${t.trip_no}`}
                          inputMode="decimal"
                          placeholder="tolls ₹"
                          value={actual[t.id]?.tolls ?? ""}
                          onChange={(e) =>
                            setActual({
                              ...actual,
                              [t.id]: { km: actual[t.id]?.km ?? "", tolls: e.target.value },
                            })
                          }
                        />
                        <button type="submit" className="btn">
                          Record
                        </button>
                      </form>
                    ) : (
                      "not back yet"
                    )}
                  </td>
                  <td className="num">
                    <Num value={t.co2} label={`estimated CO2 of ${t.trip_no}`} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Cost-to-serve and the Deal Desk (last 30 days)</h2>
      <p className="muted">
        Delivery (each customer&apos;s share of trip costs, by packets) + credit (what they owe, at
        the factory&apos;s rate of money) + returns. The floor is the lowest ex-tax price per packet
        that still covers the product and the cost of serving them.
      </p>
      {serve.length === 0 ? (
        <p className="muted">No trips in the last 30 days.</p>
      ) : (
        <div className="table-wrap">
          <table className="lines">
            <thead>
              <tr>
                <th>Customer</th>
                <th className="num">Packets</th>
                <th className="num">Delivery</th>
                <th className="num">Credit</th>
                <th className="num">Returns</th>
                <th className="num">Per packet</th>
                <th className="num">Price floor</th>
              </tr>
            </thead>
            <tbody>
              {serve.map((r) => (
                <tr key={r.customer_id}>
                  <td>{r.customer_name}</td>
                  <td className="num">{r.packets}</td>
                  <td className="num">
                    <Num value={r.delivery} label={`delivery cost of ${r.customer_name}`} />
                  </td>
                  <td className="num">
                    <Num value={r.credit} label={`credit cost of ${r.customer_name}`} />
                  </td>
                  <td className="num">
                    <Num value={r.returns} label={`returns of ${r.customer_name}`} />
                  </td>
                  <td className="num">
                    {r.per_packet ? (
                      <Num
                        value={r.per_packet}
                        label={`cost-to-serve per packet, ${r.customer_name}`}
                      />
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="num">
                    {r.price_floor ? (
                      <Num value={r.price_floor} label={`Deal Desk floor for ${r.customer_name}`} />
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
