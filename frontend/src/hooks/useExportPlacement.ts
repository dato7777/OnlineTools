import { useEffect, useState } from "react";
import { api, type PageBlock } from "@/lib/api";
import { localPlacementMetrics, type PlacementMetrics } from "@/lib/exportPlacement";

export function useExportPlacement(block: PageBlock | null): PlacementMetrics | null {
  const [metrics, setMetrics] = useState<PlacementMetrics | null>(null);

  useEffect(() => {
    if (!block || block.type !== "text") {
      setMetrics(null);
      return;
    }

    const fallback = localPlacementMetrics(block);
    setMetrics(fallback);

    const timer = setTimeout(() => {
      api
        .placementMetrics(block)
        .then(setMetrics)
        .catch(() => setMetrics(fallback));
    }, 120);

    return () => clearTimeout(timer);
  }, [
    block?.id,
    block?.content,
    block?.bbox?.[0],
    block?.bbox?.[1],
    block?.bbox?.[2],
    block?.bbox?.[3],
    block?.fontSize,
    block?.align,
    block?.tableGroupId,
  ]);

  return metrics;
}
