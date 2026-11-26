/**
 * Screen words for codes that reach the UI inside server labels: "cooking_oil" -> "cooking oil",
 * "MURUKKU-200G" -> "Murukku 200 g". Stored codes, documents and exports keep the code itself.
 */
export function plain(text: string | null | undefined): string {
  return (text ?? "")
    .replace(/\b([A-Z]{3,})-(\d+)G\b/g, (_m, name: string, grams: string) => {
      return `${name[0]}${name.slice(1).toLowerCase()} ${grams} g`;
    })
    .replace(/_/g, " ");
}
