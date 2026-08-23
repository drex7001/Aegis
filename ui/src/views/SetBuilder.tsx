import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  createObjectSet,
  evaluateObjectSet,
  listObjectSets,
  shareObjectSet,
  type ObjectSet,
  type ObjectSetEvaluation,
} from "../api/client";
import { OBJECT_TYPES, PREDICATES } from "../api/ontology";
import { entityPath } from "../routing";

/**
 * The object-set builder (T71, spec 12).
 *
 * Three things it deliberately does, each of which is a rule from the spec
 * rather than a UI preference.
 *
 * **It offers only grammar the spec defines.** Every control here maps to one
 * node kind, and the type and predicate menus come from the *generated*
 * ontology descriptors — so a new domain module's vocabulary appears with no
 * change to this file (Article XIV), and there is no free-text box that could
 * become a query language.
 *
 * **It shows what the set means, not what it returns.** A definition is the
 * saved artifact; results are computed per caller, per evaluation. The panel
 * labels the member list with the evaluation digest for that reason: two
 * people running one set legitimately see different members, and a screen that
 * implied otherwise would be teaching the wrong model.
 *
 * **It never renders a count of what it cannot show.** No totals, here or
 * anywhere — `truncated` says "there is more" without saying how much more.
 */

type Draft =
  | { kind: "type"; object_type: string }
  | { kind: "predicate"; predicate: string; direction: "subject" | "object" | "either" };

/** The AST the drafts compose to. `and` of everything, which is what a
 * filter row list means to a reader. */
function toAst(drafts: Draft[]): Record<string, unknown> {
  if (drafts.length === 1) return { ...drafts[0] };
  return { kind: "and", children: drafts.map((draft) => ({ ...draft })) };
}

export function SetBuilder() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [tracking, setTracking] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<ObjectSetEvaluation | null>(null);

  const sets = useQuery({ queryKey: ["object-sets"], queryFn: () => listObjectSets() });

  const save = useMutation({
    mutationFn: () =>
      createObjectSet({
        name,
        ast: toAst(drafts),
        track_interface_members: tracking,
      }),
    onSuccess: () => {
      setName("");
      setDrafts([]);
      void queryClient.invalidateQueries({ queryKey: ["object-sets"] });
    },
  });

  const run = useMutation({
    mutationFn: (setId: string) => evaluateObjectSet(setId),
    onSuccess: (result) => setEvaluation(result),
  });

  const share = useMutation({
    mutationFn: ({ setId, user }: { setId: string; user: string }) =>
      shareObjectSet(setId, { user_sub: user, relation: "viewer" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["object-sets"] }),
  });

  return (
    <section className="panel" data-testid="set-builder">
      <h2>Object sets</h2>
      <p className="muted">
        A set is a saved <strong>question</strong>. It stores no results: every
        evaluation runs under your own clearance, so two people can share one
        set and correctly see different members.
      </p>

      <form
        className="set-builder__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim() && drafts.length) save.mutate();
        }}
      >
        <label className="field">
          <span>Name</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            data-testid="set-name"
          />
        </label>

        <fieldset className="set-builder__filters">
          <legend>Filters</legend>
          {drafts.map((draft, index) => (
            <div key={index} className="set-builder__filter" data-testid={`filter-${index}`}>
              <code>{describe(draft)}</code>
              <button
                type="button"
                className="button button--quiet"
                onClick={() => setDrafts(drafts.filter((_, at) => at !== index))}
                data-testid={`remove-filter-${index}`}
              >
                Remove
              </button>
            </div>
          ))}

          {/*
            Two menus, both fed from the generated ontology descriptors. There
            is deliberately no free-text field: a builder that let a user type
            a condition would be a second grammar, and the one in spec 12 §2 is
            the one that gets validated.
          */}
          <div className="set-builder__add">
            <select
              defaultValue=""
              onChange={(event) => {
                if (!event.target.value) return;
                setDrafts([...drafts, { kind: "type", object_type: event.target.value }]);
                event.target.value = "";
              }}
              data-testid="add-type-filter"
            >
              <option value="">Add a type…</option>
              {Object.entries(OBJECT_TYPES).map(([name, descriptor]) => (
                <option key={name} value={name}>
                  {descriptor.label}
                </option>
              ))}
            </select>

            <select
              defaultValue=""
              onChange={(event) => {
                if (!event.target.value) return;
                setDrafts([
                  ...drafts,
                  { kind: "predicate", predicate: event.target.value, direction: "either" },
                ]);
                event.target.value = "";
              }}
              data-testid="add-predicate-filter"
            >
              <option value="">Add a connection…</option>
              {Object.keys(PREDICATES).map((predicate) => (
                <option key={predicate} value={predicate}>
                  {predicate}
                </option>
              ))}
            </select>
          </div>
        </fieldset>

        <label className="field field--inline">
          <input
            type="checkbox"
            checked={tracking}
            onChange={(event) => setTracking(event.target.checked)}
            data-testid="track-interface-members"
          />
          <span>
            Follow future interface members
            <small className="muted">
              {" "}
              — off by default, so this set keeps meaning what it means today
              even after a new object type is declared.
            </small>
          </span>
        </label>

        <button
          type="submit"
          className="button"
          disabled={!name.trim() || drafts.length === 0 || save.isPending}
          data-testid="save-set"
        >
          {save.isPending ? "Saving…" : "Save set"}
        </button>
        {save.isError && (
          <p className="error" data-testid="set-error">
            {String(save.error)}
          </p>
        )}
      </form>

      <h3>Saved sets</h3>
      {sets.data?.items.length === 0 && (
        <p className="muted" data-testid="no-sets">
          No sets you can see.
        </p>
      )}
      <ul className="set-builder__list" data-testid="set-list">
        {sets.data?.items.map((row) => (
          <li key={row.set_id} data-testid={`set-${row.set_id}`}>
            <SetRow
              row={row}
              onRun={() => {
                setSelected(row.set_id);
                run.mutate(row.set_id);
              }}
              onShare={(user) => share.mutate({ setId: row.set_id, user })}
            />
          </li>
        ))}
      </ul>

      {evaluation && selected && (
        <Results evaluation={evaluation} />
      )}
    </section>
  );
}

function describe(draft: Draft): string {
  return draft.kind === "type"
    ? `type = ${draft.object_type}`
    : `${draft.direction} of ${draft.predicate}`;
}

function SetRow({
  row,
  onRun,
  onShare,
}: {
  row: ObjectSet;
  onRun: () => void;
  onShare: (user: string) => void;
}) {
  const [recipient, setRecipient] = useState("");
  return (
    <div className="set-builder__row">
      <div>
        <strong>{row.name}</strong>
        <span className="muted">
          {" "}
          v{row.latest.version} · pinned to ontology {row.latest.ontology_version}
          {row.latest.track_interface_members ? " · following new members" : ""}
        </span>
      </div>
      <div className="set-builder__actions">
        <button
          type="button"
          className="button"
          onClick={onRun}
          data-testid={`run-${row.set_id}`}
        >
          Evaluate
        </button>
        <input
          placeholder="Share with…"
          value={recipient}
          onChange={(event) => setRecipient(event.target.value)}
          data-testid={`share-input-${row.set_id}`}
        />
        <button
          type="button"
          className="button button--quiet"
          disabled={!recipient.trim()}
          onClick={() => {
            onShare(recipient.trim());
            setRecipient("");
          }}
          data-testid={`share-${row.set_id}`}
        >
          Share
        </button>
      </div>
    </div>
  );
}

/**
 * The members this caller sees, labelled with the digest that identifies them.
 *
 * The digest is not decoration. Two people evaluating one set get different
 * digests when their clearances differ, and an analytic finding records the
 * digest of the set it was computed over — so "the same inputs" is checkable
 * rather than hoped (ADR-055). Showing it here is what makes that legible
 * before somebody compares two findings and wonders why they disagree.
 */
function Results({ evaluation }: { evaluation: ObjectSetEvaluation }) {
  return (
    <div className="panel panel--nested" data-testid="set-results">
      <h3>
        Members <span className="muted">— as you can see them</span>
      </h3>
      <p className="muted">
        Evaluation <code data-testid="evaluation-digest">{evaluation.evaluation_digest.slice(0, 12)}</code>
        {evaluation.truncated && " · more members than shown"}
      </p>
      <ul className="set-builder__members">
        {evaluation.members.map((member) => (
          <li key={member.entity_id}>
            <Link to={entityPath(member.entity_id)} data-testid={`member-${member.entity_id}`}>
              {member.label}
            </Link>
            <span className="muted"> {member.entity_type}</span>
          </li>
        ))}
      </ul>
      {evaluation.members.length === 0 && (
        <p className="muted" data-testid="no-members">
          Nothing you are cleared to see matches this set.
        </p>
      )}
    </div>
  );
}
