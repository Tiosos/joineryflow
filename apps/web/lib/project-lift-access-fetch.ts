import type { ProjectLiftAccessOut, UpsertLiftAccessIn } from "./pm-types";
import { apiCall, jsonInit } from "./api";

// PUT is a full overwrite, not a partial merge (project_lift_access/queries.py
// upsert_lift_access sets both columns from the body every time) — callers
// must always send both `notes` and `sketch_file_blob_id` together, not just
// the one field being changed.
export const liftAccessApi = {
  upsert: (projectId: number, body: UpsertLiftAccessIn) =>
    apiCall<ProjectLiftAccessOut>(`/api/projects/${projectId}/lift-access`, jsonInit("PUT", body)),
};
