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
  /** Live comments on the task's thread (a deleted one is not counted). */
  comment_count: number;
  /** May the caller post in the thread (the task's target module's `comment` grant, or any person
   *  on a task with no target). Reading it needs only that the caller can see the task. */
  can_comment: boolean;
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
