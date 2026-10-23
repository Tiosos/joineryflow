import type { ProjectContract, VariationItem } from "./project-contract-types";
import type { TrackingGridOut } from "./pm-types";
import { apiCall, jsonInit } from "./api";

export const projectContractApi = {
  addVariation: (projectId: number, description: string, amountDelta: string, itemIds: number[] = []) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations`,
      jsonInit("POST", { description, amount_delta: amountDelta, item_ids: itemIds }),
    ),
  editVariation: (
    projectId: number,
    variationId: number,
    changes: { description?: string; amount_delta?: string; item_ids?: number[] },
  ) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations/${variationId}`,
      jsonInit("PATCH", changes),
    ),
  decideVariation: (projectId: number, variationId: number, decision: "approved" | "rejected", note?: string) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations/${variationId}/decision`,
      jsonInit("POST", { decision, note: note ?? null }),
    ),
  /** The project's Joinery Items a variation can be linked to (related parts cannot). */
  linkableItems: async (projectId: number): Promise<VariationItem[]> => {
    const grid = await apiCall<TrackingGridOut>(`/api/projects/${projectId}/items`);
    return grid.items
      .filter((i) => i.row_type === "joinery_item" && i.item_number != null)
      .map((i) => ({ item_id: i.id, num: i.item_number as number, description: i.description }));
  },
};
