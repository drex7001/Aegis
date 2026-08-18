import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, listTasks, openTask, updateTask, type Task } from "../api/client";

/**
 * Tasks and leads on the case screen (T48).
 *
 * Status columns, and nothing more. There is no workflow engine, no approval
 * chain and no transition graph — plan §2's trigger stays untouched — so any
 * status may follow any other and the server audits each move with its old
 * value beside the new one. That audit row is what makes the history
 * answerable; a state machine here would be a rule with no rule-maker.
 *
 * A *task* is work to do and a *lead* is a line of enquiry worth pursuing. One
 * list, one `kind` chip, because the only difference is the word.
 */

const STATUSES = ["open", "in_progress", "blocked", "done", "dropped"] as const;

export function CaseTasks({ caseId }: { caseId: string }) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const tasks = useQuery({ queryKey: ["tasks", caseId], queryFn: () => listTasks(caseId) });
  const refresh = () => void client.invalidateQueries({ queryKey: ["tasks", caseId] });
  const fail = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.message : fallback);

  const create = useMutation({
    mutationFn: (body: { title: string; kind: "task" | "lead"; owner: string | null }) =>
      openTask({ case_id: caseId, ...body }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (err: unknown) => fail(err, "Could not open the task."),
  });

  const move = useMutation({
    mutationFn: (change: { taskId: string; status: string }) =>
      updateTask(change.taskId, { status: change.status as never }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (err: unknown) => fail(err, "Could not move the task."),
  });

  const byStatus = new Map<string, Task[]>(STATUSES.map((status) => [status, []]));
  for (const task of tasks.data ?? []) {
    byStatus.get(task.status)?.push(task);
  }

  return (
    <>
      <h2>Tasks and leads</h2>
      {error && (
        <p className="notice notice--error" role="alert" data-testid="task-error">
          {error}
        </p>
      )}

      <div className="task-board" data-testid="task-board">
        {STATUSES.map((status) => (
          <section key={status} className="task-board__column" data-testid={`tasks-${status}`}>
            <h3>{status.replace("_", " ")}</h3>
            {(byStatus.get(status) ?? []).length === 0 ? (
              <p className="muted">—</p>
            ) : (
              <ul>
                {(byStatus.get(status) ?? []).map((task) => (
                  <li key={task.task_id} data-testid={`task-${task.task_id}`}>
                    <span className="chip chip--kind">{task.kind}</span> {task.title}
                    <span className="muted">
                      {" "}
                      · {task.owner ?? "unassigned"}
                      {task.due_date && ` · due ${task.due_date}`}
                    </span>
                    <select
                      value={task.status}
                      aria-label={`Status of ${task.title}`}
                      data-testid={`task-status-${task.task_id}`}
                      onChange={(event) =>
                        move.mutate({ taskId: task.task_id, status: event.target.value })
                      }
                    >
                      {/* Every status offered from every status: the absence of
                          a transition graph is the design, not an omission. */}
                      {STATUSES.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      <form
        className="case-form"
        data-testid="task-form"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          create.mutate({
            title: String(form.get("title") ?? ""),
            kind: form.get("kind") === "lead" ? "lead" : "task",
            // Empty means unassigned, which is a real state — not a reason to
            // invent an owner so the queue looks attended.
            owner: String(form.get("owner") ?? "") || null,
          });
          event.currentTarget.reset();
        }}
      >
        <label>
          <span>Title</span>
          <input name="title" required data-testid="task-title" />
        </label>
        <label>
          <span>Kind</span>
          <select name="kind" data-testid="task-kind">
            <option value="task">task</option>
            <option value="lead">lead</option>
          </select>
        </label>
        <label>
          <span>Owner</span>
          <input name="owner" data-testid="task-owner" />
        </label>
        <button type="submit" data-testid="task-open">
          Add
        </button>
      </form>
    </>
  );
}
