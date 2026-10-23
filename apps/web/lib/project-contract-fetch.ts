import type { ProjectContract, VariationItem } from "./project-contract-types";
import type { TrackingGridOut } from "./pm-types";
import { apiCall, jsonInit } from "./api";

/** `amount_delta` is the selling-price impact; empty optional fields are omitted. */
export interface NewVariation {
  description: string;
  amount_delta: string;
  reason: string;
  requester?: string;
  requested_on?: string;
  cost_impact?: string;
  time_impact_days?: number;
  item_ids?: number[];
}

export const projectContractApi = {
  addVariation: (projectId: number, body: NewVariation) =>
    apiCall<ProjectContract>(`/api/projects/${projectId}/contract/variations`, jsonInit("POST", body)),
  editVariation: (
    projectId: number,
    variationId: number,
    changes: Partial<
      Omit<NewVariation, "requester" | "requested_on" | "cost_impact" | "time_impact_days"> & {
        requester: string | null;
        requested_on: string | null;
        cost_impact: string | null;
        time_impact_days: number | null;
      }
    >,
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
  voidVariation: (projectId: number, variationId: number, reason: string) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations/${variationId}/void`,
      jsonInit("POST", { reason }),
    ),
  /** The project's Joinery Items a variation can be linked to (related parts cannot). */
  linkableItems: async (projectId: number): Promise<VariationItem[]> => {
    const grid = await apiCall<TrackingGridOut>(`/api/projects/${projectId}/items`);
    return grid.items
      .filter((i) => i.row_type === "joinery_item" && i.item_number != null)
      .map((i) => ({ item_id: i.id, num: i.item_number as number, description: i.description }));
  },
};
