# Data — two strictly separated tracks

| Track | Path | Nature |
|---|---|---|
| Real corpus | [`real/`](real/) | **Real people, public reporting only.** Read [`real/README.md`](real/README.md) before touching anything — provenance and ethics rules are binding. |
| Sample data | [`sample/`](sample/) | **Fictional** test data, safe for demos and tests. |

Rules (AGENTS.md, GOAL.md §24):

- Never add national-ID numbers for real persons.
- Never present association as guilt (Article IX).
- Everything in `real/` must be citable to public reporting; the corpus files
  themselves stay untracked (only `real/README.md` is committed).
- Raw source material (PDFs, video, audio) lands in the gitignored `Files/`
  drop zone and is ingested via the toolchain in `docs/INGESTION.md`.
