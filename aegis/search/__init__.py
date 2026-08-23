"""Global search over entities, claims and documents (spec 11, ADR-050…053).

One route, `GET /v1/search`. One normalization pipeline, versioned and applied
identically at write and query time. Three backends behind it, each responsible
for one kind of thing and all ranked onto the same 0–1 scale.

**Authorization is applied in candidate generation, never after hydration.**
This paragraph used to say the opposite — "results return ids only;
authorization is re-checked before hydration" — which is the pre-amendment
wording B-17 rejects, and which the code has not matched since T23c. Generating
candidates and filtering afterwards answers "no results" and "results you may
not see" with different response sizes, and that difference is readable through
ranking, counts, pagination gaps and timing.

| Module | Responsibility |
|---|---|
| `pipeline` | the one entry point that turns text into keys, and the version stamped on every stored key (ADR-052) |
| `entities` | labels, aliases, and the mention keys that let a romanized query reach a Sinhala name (ADR-035) |
| `claims` | excerpts and literal values, with identifiers matched exactly and never fuzzily (ADR-053) |
| `documents` | full text over the projection, because the text is not in Postgres (ADR-051) |
| `service` | one ranked page across all three; groups are how it is *displayed*, never how it is fetched |
| `results` | the shared hit shape and the single ordering the cursor is built from |
| `targets`, `quality` | the numbers the phase is gated on, and what measures them (H-22) |

Quality is tracked by the golden Sinhala/Tamil/English set. OpenSearch replaces
the backend only if the ADR-012 trigger fires — measured, in `targets.py`,
beside the numbers that watch it.
"""
