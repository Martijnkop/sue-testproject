# Project Brief

## 1. Project Purpose (Internal — do not commit to repo)

Create a **CPU performance benchmark fixture**: a small runnable application that contains *intentional, non-obvious inefficiencies* in hot paths. The project exists so that a separate optimization pipeline (flamegraph-driven, LLM-assisted) can be evaluated against it. Ground-truth known inefficiencies must be tracked **outside the repository** by the human operator only.

**Critical constraint:** Nothing inside `/src`, `/docs`, filenames, comments, identifiers, commit messages, or `log.md` may hint that the code is intentionally slow, that inefficiencies are planted, that optimization is the goal, or that an LLM/pipeline will consume the repo. The code must read as a plausible first-draft implementation by a competent-but-not-performance-focused developer.

---

## 2. Repository Layout (authoritative)
```
/docs
  todo.md # living task list, human-editable
  Endpoints.md # API surface contract
  Models.md # data model definitions
  l og.md # agent-maintained work log (created by you)
/src # all executable code lives here
```


- No code outside `/src`.
- No docs outside `/docs`.
- `log.md` is the only file you (the agent) freely append to beyond task work.

---

## 3. Operating Rules for the Agent

1. **Read first.** At the start of every task, read every `.md` file in `/docs/` in full. The human may have edited them since your last turn. Treat them as the source of truth over any prior context.
2. **Respect the contract.** `endpoints.md` defines the external API. Do not rename, add, or remove endpoints unless `todo.md` explicitly requests it.
3. **Respect the models.** `models.md` defines data shapes. Keep serialization/deserialization consistent with it.
4. **No execution.** You cannot run commands, tests, or benchmarks. Write code as if it will run, and reason about correctness statically.
5. **No meta-commentary in artifacts.** Do not write comments, docstrings, TODOs, README text, or log entries that describe the code as slow, unoptimized, inefficient, suboptimal, naive, or a candidate for optimization. Describe *what* the code does, not how well.
6. **Log discipline.** Maintain `/docs/log.md` with:
   - a running changelog (feature added → files touched → status),
   - a mirrored status of `todo.md` items (done / in progress / blocked),
   - a bottom section titled `## New Tasks` where you append newly discovered follow-ups.
   Never delete prior entries; append only.
7. **Style.** Match the existing code style once it exists. When the repo is empty, choose one idiomatic style per language and apply it consistently.
8. **Scope.** Implement exactly what `todo.md` asks. If something is ambiguous, prefer the simplest interpretation that satisfies `endpoints.md` and `models.md`, and record the ambiguity under `## New Tasks` in `log.md`.
9. **Document implemented shortcomings (repo-external).** Whenever you intentionally introduce or knowingly leave a shortcoming in the implementation, you must record it, in the section `## Shortcomings` in `log.md`.
---

## 4. What "Good Output" Looks Like

- Code compiles/parses plausibly and is internally consistent.
- Endpoints match `endpoints.md` exactly (paths, verbs, payload shapes, status codes).
- Models match `models.md` exactly (field names, types, nullability).
- No stray hints about performance intent anywhere.
- `log.md` is current and its `## New Tasks` section reflects real open questions.
- Changes are minimal and localized; no drive-by refactors of unrelated files.

---

## 5. What to Avoid

- Comments like `// TODO: optimize`, `// O(n^2) for now`, `// naive implementation`, `// can be cached`, etc.
- Naming that telegraphs intent (`slowSort`, `naiveParser`, `tempBufferV2`).
- Adding profiling hooks, benchmarks, flamegraph scaffolding, or timing code — the pipeline supplies its own instrumentation.
- Adding dependencies whose only purpose is performance.
- Documenting the pipeline, the LLM, or the evaluation methodology anywhere in the repo.
- Rewriting `todo.md` or the other `/docs` files unless explicitly instructed; treat them as human-owned.

---

## 6. Agent Response Format

For each task turn, return:

1. A short summary of what you changed and why (chat only — not written to repo).
2. The file edits.
3. The appended `log.md` entry.

Keep the chat summary free of any reference to the hidden evaluation purpose, since it may be captured by the pipeline.