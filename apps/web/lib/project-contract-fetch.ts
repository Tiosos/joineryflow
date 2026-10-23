import type { ProjectContract } from "./project-contract-types";
import { apiCall, jsonInit } from "./api";

export const projectContractApi = {
  addVariation: (projectId: number, description: string, amountDelta: string) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations`,
      jsonInit("POST", { description, amount_delta: amountDelta }),
    ),
  editVariation: (projectId: number, variationId: number, description: string, amountDelta: string) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations/${variationId}`,
      jsonInit("PATCH", { description, amount_delta: amountDelta }),
    ),
  decideVariation: (projectId: number, variationId: number, decision: "approved" | "rejected", note?: string) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations/${variationId}/decision`,
      jsonInit("POST", { decision, note: note ?? null }),
    ),
};
