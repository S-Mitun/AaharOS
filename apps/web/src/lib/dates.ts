/** YYYY-MM-DD in the user's own time zone (toISOString() is UTC, which is still "yesterday" before 05:30 in India). */
export function localDate(d: Date = new Date()): string {
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
