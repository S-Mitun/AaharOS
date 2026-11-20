import { createContext, useContext } from "react";
import type { GuideData } from "./guideData";

export const GuideDataContext = createContext<GuideData | null>(null);

export function useGuideData(): GuideData {
  const ctx = useContext(GuideDataContext);
  if (!ctx) throw new Error("useGuideData must be used inside GuideDataProvider");
  return ctx;
}
