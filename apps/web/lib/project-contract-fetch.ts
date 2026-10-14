import type { ProjectContract } from "./project-contract-types";
import { apiCall, jsonInit } from "./api";

export const projectContractApi = {
  addVariation: (projectId: number, description: string, amountDelta: string) =>
    apiCall<ProjectContract>(
      `/api/projects/${projectId}/contract/variations`,
      jsonInit("POST", { description, amount_delta: amountDelta }),
    ),
};
