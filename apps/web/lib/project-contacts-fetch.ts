import type { CreateContactIn, PatchContactIn, ProjectContactOut } from "./pm-types";
import { apiCall, jsonInit } from "./api";

export const projectContactsApi = {
  create: (projectId: number, body: CreateContactIn) =>
    apiCall<ProjectContactOut>(`/api/projects/${projectId}/contacts`, jsonInit("POST", body)),
  patch: (contactId: number, body: PatchContactIn) =>
    apiCall<ProjectContactOut>(`/api/contacts/${contactId}`, jsonInit("PATCH", body)),
  remove: (contactId: number) =>
    apiCall<void>(`/api/contacts/${contactId}`, { method: "DELETE" }),
};
