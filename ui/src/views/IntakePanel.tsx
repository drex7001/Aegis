import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import {
  ApiError,
  createSource,
  getVocabulary,
  landFile,
  landText,
  listSources,
  type LandingResult,
} from "../api/client";

/**
 * Raw landing (spec 04 §1 stage 1) from the browser.
 *
 * The form's job is to make the provenance envelope worth having. Every
 * optional field left blank is a question about this artifact nobody can answer
 * later, so each one says what it is for rather than just naming itself — and
 * blanks are sent as absent, not as empty strings, because "collected from
 * nowhere" is a claim and an untouched input does not make it.
 */

type Mode = "file" | "text";

export function IntakePanel({ onLanded }: { onLanded: (result: LandingResult) => void }) {
  const [mode, setMode] = useState<Mode>("file");
  const queryClient = useQueryClient();

  const vocabulary = useQuery({ queryKey: ["vocabulary"], queryFn: getVocabulary });
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => listSources({ limit: 200 }),
  });

  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [handling, setHandling] = useState("open");
  const [sourceUrl, setSourceUrl] = useState("");
  const [policy, setPolicy] = useState("");
  const [notes, setNotes] = useState("");

  const landing = useMutation({
    mutationFn: async (): Promise<LandingResult> => {
      const shared = {
        source_id: sourceId || undefined,
        handling_code: handling,
        source_url: sourceUrl || undefined,
        collection_policy: policy || undefined,
        notes: notes || undefined,
      };
      return mode === "file"
        ? landFile({ file: file as File, ...shared })
        : landText({ text, filename, ...shared });
    },
    onSuccess: (result) => {
      onLanded(result);
      void queryClient.invalidateQueries({ queryKey: ["source-records"] });
    },
  });

  const ready = mode === "file" ? file !== null : text.trim() !== "" && filename.trim() !== "";

  return (
    <section className="intake" aria-labelledby="intake-heading">
      <header className="intake__head">
        <h1 id="intake-heading">Land a source record</h1>
        <p className="muted">
          Bytes go to the vault unchanged. What you enter here travels with them
          and is what anyone checking a claim will read.
        </p>
      </header>

      <div className="tabs" role="tablist" aria-label="How to add the record">
        {(["file", "text"] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            className={`tab${mode === value ? " tab--active" : ""}`}
            onClick={() => setMode(value)}
          >
            {value === "file" ? "Upload a file" : "Paste text"}
          </button>
        ))}
      </div>

      <form
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          landing.mutate();
        }}
      >
        {mode === "file" ? (
          <Field label="File" hint="PDFs are readable today; other formats land but cannot be extracted yet.">
            <input
              type="file"
              data-testid="intake-file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </Field>
        ) : (
          <>
            <Field
              label="Name this record"
              hint="How you will recognise it later, and half of what makes re-pasting the same text a no-op."
            >
              <input
                type="text"
                value={filename}
                placeholder="field-note.txt"
                data-testid="intake-filename"
                onChange={(event) => setFilename(event.target.value)}
              />
            </Field>
            <Field label="Text">
              <textarea
                rows={6}
                value={text}
                data-testid="intake-text"
                onChange={(event) => setText(event.target.value)}
              />
            </Field>
          </>
        )}

        <SourceField
          sources={sources.data?.items ?? []}
          sourceTypes={vocabulary.data?.source_types ?? []}
          value={sourceId}
          onChange={setSourceId}
        />

        <Field label="Handling" hint="Who may see this record. You cannot land above your own clearance.">
          <select
            value={handling}
            data-testid="intake-handling"
            onChange={(event) => setHandling(event.target.value)}
          >
            {(vocabulary.data?.handling_codes ?? ["open"]).map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Collected from" hint="The address this came from, if it has one.">
          <input
            type="url"
            value={sourceUrl}
            placeholder="https://…"
            data-testid="intake-url"
            onChange={(event) => setSourceUrl(event.target.value)}
          />
        </Field>

        {/*
          Source, handling and origin are decisions with consequences — who may
          read this, and whether a claim from it can be checked. Policy and
          notes are annotations. Folding the annotations keeps the submit button
          and its answer on screen without hiding anything an operator has to
          choose; `<details>` because a native disclosure is keyboard- and
          screen-reader-correct with no code.
        */}
        <details className="more">
          <summary>Collection details</summary>
          <Field label="Collection policy" hint="The policy this was collected under.">
            <input
              type="text"
              value={policy}
              placeholder="public-osint-v1"
              onChange={(event) => setPolicy(event.target.value)}
            />
          </Field>

          <Field label="Notes">
            <input
              type="text"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </Field>
        </details>

        <button
          type="submit"
          className="button button--primary"
          data-testid="intake-submit"
          disabled={!ready || landing.isPending}
        >
          {landing.isPending ? "Landing…" : mode === "file" ? "Land file" : "Land text"}
        </button>
      </form>

      {landing.error && <Problem error={landing.error} />}
    </section>
  );
}

/**
 * One control, labelled implicitly by wrapping it.
 *
 * Wrapping rather than `htmlFor` keeps the association correct without every
 * caller having to mint and thread an id, and it cannot drift out of sync.
 */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <label className="field__label">
        <span className="field__name">{label}</span>
        {children}
      </label>
      {hint && <p className="field__hint">{hint}</p>}
    </div>
  );
}

/**
 * The source picker, with creation inline.
 *
 * Sending an operator to a different screen to register a source, mid-upload,
 * is how artifacts end up under "Manual upload" forever.
 */
function SourceField({
  sources,
  sourceTypes,
  value,
  onChange,
}: {
  sources: Array<{ source_id: string; name: string }>;
  sourceTypes: string[];
  value: string;
  onChange: (id: string) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState("");
  const queryClient = useQueryClient();

  // The vocabulary arrives asynchronously, so "the first source type" is not a
  // value that exists at first render. An empty string here disables Add rather
  // than posting a source with no type.
  const selectedType = type || sourceTypes[0] || "";

  const create = useMutation({
    mutationFn: () => createSource({ name, source_type: selectedType }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
      onChange(created.source_id);
      setCreating(false);
      setName("");
    },
  });

  // Written out rather than passed through `Field`: this row holds a control
  // *and* a button, and a button inside a <label> hijacks clicks meant for it.
  const selectId = useId();

  return (
    <div className="field">
      <label className="field__label" htmlFor={selectId}>
        <span className="field__name">Source</span>
      </label>
      {creating ? (
        <div className="inline-create">
          <input
            type="text"
            value={name}
            aria-label="Source name"
            placeholder="Source name"
            onChange={(event) => setName(event.target.value)}
          />
          <select
            value={selectedType}
            aria-label="Source type"
            onChange={(event) => setType(event.target.value)}
          >
            {sourceTypes.map((option) => (
              <option key={option} value={option}>
                {option.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => create.mutate()}
            disabled={name.trim() === "" || selectedType === "" || create.isPending}
          >
            Add
          </button>
          <button type="button" onClick={() => setCreating(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <div className="inline-create">
          <select
            id={selectId}
            value={value}
            data-testid="intake-source"
            onChange={(event) => onChange(event.target.value)}
          >
            <option value="">Manual upload</option>
            {sources.map((source) => (
              <option key={source.source_id} value={source.source_id}>
                {source.name}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => setCreating(true)}>
            New source
          </button>
        </div>
      )}
      <p className="field__hint">
        Who published or produced this. A source&rsquo;s reliability is graded
        separately from any single claim&rsquo;s credibility.
      </p>
      {create.error && <Problem error={create.error} />}
    </div>
  );
}

function Problem({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError ? error.message : "The record could not be landed.";
  return (
    <p className="outcome outcome--error" role="alert" data-testid="intake-error">
      {message}
    </p>
  );
}
