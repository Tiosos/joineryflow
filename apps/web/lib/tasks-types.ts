// Mirrors apps/api/app/tasks/schemas.py. Dates are `YYYY-MM-DD` / ISO strings; ids are numbers.

export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";
export type TaskTargetType = "project" | "item" | "cutlist";

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  done: "Done",
  cancelled: "Cancelled",
};

export interface TaskOut {
  task_id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  assignee_id: number | null;
  assignee_name: string | null;
  created_by: number;
  created_by_name: string | null;
  due_date: string | null;
  source: string;
  project_id: number | null;
  item_id: number | null;
  cutlist_id: number | null;
  target_type: TaskTargetType | null;
  target_label: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  field_versions: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface TaskList {
  items: TaskOut[];
  total: number;
}

export interface CreateTaskBody {
  title: string;
  description?: string | null;
  assignee_id?: number | null;
  due_date?: string | null;
  project_id?: number | null;
  item_id?: number | null;
  cutlist_id?: number | null;
}

export interface PatchTaskBody {
  title?: string;
  description?: string | null;
  assignee_id?: number | null;
  due_date?: string | null;
  expected_versions?: Record<string, number>;
}

/** What the bell shows for a task: the caller's own, still to do. */
export interface TaskOpen {
  task_id: number;
  title: string;
  status: string;
  due_date: string | null;
  target_label: string | null;
  url: string;
}
