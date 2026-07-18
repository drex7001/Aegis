# Real data — provenance & ethics

This folder holds the **real** input corpus for Aegis's first application domain —
criminal-network analysis of documented Sri Lankan cases. Unlike `data/sample/` (which
is fictional and exists only to exercise the regex/structural pass), everything here is
compiled from **public reporting** about documented cases.

## What's here

| File | Role |
|---|---|
| `narcotics_network.txt` | Narrative intelligence-style summary of the transnational drug network — input for the **live LLM (semantic) pass**. |
| `easter_attacks_network.txt` | Narrative summary of the 2019 Easter Sunday / NTJ network — input for the semantic pass. |

The authoritative, fully-cited node/edge set lives in code at
[`legacy/pipeline/real_dataset.py`](../../legacy/pipeline/real_dataset.py) (the deterministic **curated OSINT layer**).
The legacy graph builder is reference-only; the platform path imports this
curated corpus with `aegis migrate-legacy` and rebuilds views with
`aegis projections rebuild`.

## Sources

All facts trace to public reporting, principally:

- Wikipedia — *List of Sri Lankan mobsters*
- Wikipedia — *2019 Sri Lanka Easter bombings*
- Jamestown Foundation — brief on Zahran Hashim / NTJ
- Ada Derana, Daily Mirror, News First, dbsjeyaraj.com, Times of Addu, Lanka News Web, Tamil Guardian

Each node and edge carries its own `source_file` citation (see the `SOURCES` map in
`legacy/pipeline/real_dataset.py`), surfaced in the UI's **Sources** panel and each entity's detail card.

## Ethics & honesty rules

- **Open-source only.** Nothing here asserts anything beyond what the cited public reporting says.
- **Not a determination of guilt.** This is an analytical model for lawful network analysis.
- **Confidence tags encode source strength**, following the Graphify honesty rule *never invent an edge*:
  - `EXTRACTED` (1.0) — stated plainly in an official record or by named reporting (e.g. "arrested together in Dubai, 4 Feb 2019").
  - `INFERRED` (0.7) — probable link reporting supports but has not adjudicated (e.g. "partnered to control maritime routes").
  - `AMBIGUOUS` (0.4) — alleged / contested / uncorroborated (e.g. Islamic State *direction* of the attacks, which the CID did not establish; the "80 politicians" allegation).
- **National ID numbers are deliberately omitted**, even where reported.
- **The three networks are kept separate** (historical Colombo underworld · modern transnational narcotics · 2019 Easter/NTJ extremism) because the public record does **not** link them. Community detection recovering them as distinct cells is the analytical finding — not an assertion of a super-network.

Most individuals modelled here are deceased, convicted, or charged in matters of extensive
public record (a terrorist attack examined by a Presidential Commission of Inquiry, and
narcotics cases reported nationally).
