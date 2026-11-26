/** GST state codes to the state's name, for screen text (the code stays in documents and exports). */
const STATES: Record<string, string> = {
  "29": "Karnataka",
  "32": "Kerala",
  "33": "Tamil Nadu",
  "34": "Puducherry",
  "36": "Telangana",
  "37": "Andhra Pradesh",
};

export const stateName = (code: string | null | undefined) =>
  code ? (STATES[code] ?? `State ${code}`) : "";
