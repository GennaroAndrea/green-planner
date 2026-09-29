# Phase 4 (demo readiness): review and handoff

- **Date**: 2026-09-29
- **Phase**: 4, demo readiness (plan §8, items 4.1–4.4)
- **Status**: done, except the checks only the user can run: a real phone over ngrok, and the first Render deploy (it needs the push). Q51–Q52 were decided during this phase.
- **Next phase**: 5 (stretch), or the team joining (§8.1)

---

## Part A: Review

### A.1 What was built

| Plan item | Result | Where |
|---|---|---|
| 4.1 One-command demo | `make demo` runs `scripts/demo.sh`, which does five things in order. (1) Checks tools and that the port is free. (2) Runs `uv sync --frozen`. (3) Picks the data: `data/processed/`, else a rebuild from `data/raw/`, else the committed snapshot `deploy/data/`. It warns if the snapshot differs from `data/processed/`. (4) Runs `npm ci` if `node_modules` is missing, and rebuilds the frontend only if a source file is newer than `dist/index.html`. (5) Starts uvicorn on 127.0.0.1:8080 (log in `data/interim/demo_uvicorn.log`), waits for `/api/health`, then starts `ngrok http 8080 --url https://green-planner.ngrok.io`. Ctrl+C stops both (EXIT trap). `make demo-local` does the same without ngrok. Without a terminal, ngrok logs plain lines (`--log stdout`). | `Makefile`, `scripts/demo.sh` |
| (Q51) Render fallback | A multi-stage `Dockerfile` (node:24-slim builds the frontend; python:3.12-slim + uv 0.12.20 runs `uv sync --frozen --no-dev`) serves the app on `$PORT` with `GREEN_PLANNER_DATA_DIR=/app/deploy/data`. `render.yaml` is a Blueprint: free plan, Frankfurt, health check `/api/health`, auto-deploy. `make snapshot` copies what the backend loads (metadata, parquet files, layer GeoJSONs: 1.7 MB) into `deploy/data/`. `make docker-build` / `docker-run` test the image locally. | `Dockerfile`, `.dockerignore`, `render.yaml`, `deploy/` |
| 4.2 Checks | Load time over ngrok and NFR-10 device emulation (A.2). Two landscape-phone fixes: the legend starts collapsed when the viewport is < 500 px tall, and the header hides its subtitle and the "Metodologia e fonti" label below 768 px (was 640 px). | `frontend/src/App.tsx`, `frontend/src/components/Header.tsx` |
| 4.3 Demo script | Italian (Q52), about 3 minutes. Pre-demo checklist, then Madonnella → Libertà (satellite vs public green, simulator) → Loseto → weights + robustness → cells + methodology. Also covers what to do if ngrok or the internet fails, and likely jury questions with short answers. | `docs/demo_script.md` |
| 4.4 README | "Demo" and "Fallback deploy on Render" sections, and the layout gains `scripts/` and `deploy/`. No slides (Q52). `CLAUDE.md` lists the new docs and commands. | `README.md`, `CLAUDE.md` |

### A.2 Results and how they were verified

- **ngrok**: with the reserved domain there is **no free-plan warning page**. A curl with an iPhone Safari user agent gets the app HTML directly.
- **Load time over ngrok** (headless Chrome, 1366×768, cold cache, 3 runs each; "ready" = legend class counts shown and map canvas present):
  - no throttling: 1.16–1.43 s (network idle 2.1–2.8 s);
  - Fast 4G emulation (9 Mbit/s, 60 ms): 1.21–1.37 s;
  - Slow 4G emulation (1.6 Mbit/s, 150 ms): 2.88–3.22 s (network idle about 5.9 s);
  - about 644 KB transferred per load, and 0 console errors.
  - **NFR-04 (< 3 s on a laptop via ngrok) is met.** No bundle optimisation was needed (phase 3 A.5 item 5 can stay open).
- **NFR-10 device emulation over ngrok**, each device loaded then Libertà selected from the list: iPhone SE 375×667 / 667×375, Pixel 7 412×915 / 915×412, iPad 820×1180 / 1180×820, 1366×768, 1920×1080. Result: no horizontal scroll and 0 console errors everywhere. The screenshots showed the landscape-phone problems fixed in 4.2 (at 667×375 the open legend covered most of the map and the header wrapped). They were re-checked after the fix.
- **Launcher**:
  - `make demo` with built data and dist: tunnel up about 2 s after launch.
  - After ngrok stopped, the public URL returned 404 and the backend was gone (the trap works).
  - **Clean start** (a copy with no `.venv`, `node_modules`, `dist`, `data/processed` or `data/raw`): ready in **7 s** from the snapshot, with the uv and npm caches warm. It served Madonnella as 1st.
- **Docker image** (the Render deploy, built locally): the build takes about 90 s, and the image is 2.19 GB uncompressed. Run with `-m 512m` (the Render free limit) and `PORT=10000`:
  - ready in 1.3 s;
  - 161 MiB used after the default requests, 190 MiB after 9 custom-weight sensitivity runs (all levels);
  - the zone top 5 matches `data/processed/`.
  - The scenario cache is LRU-bounded (`SCENARIO_CACHE_SIZE`), so memory doesn't grow without limit.
- **Demo numbers** were re-read from the API at default weights (data `built_at` 2026-09-29T20:33). They match methodology §13 and phase 3 A.6:
  - Madonnella: 97,0, 1st, rank interval 1–1, vegetation 1,9%, 508 trees;
  - Libertà: 91,5, 4th, 4–4, vegetation 3,0% vs 20,9% public green, 1,678 + 113 trees;
  - Libertà simulator: 1,678 trees → 87,1 medio-alta, 4th; 6,763 trees → 73,9 media, 11th;
  - Loseto: 55,5, 16th, 14–16;
  - zone totals: 32,933 + 12,345 trees; Spearman mean 0.9972, 15/16 robust;
  - weights 10/60/10/20: the top 4 are Madonnella, San Nicola, Murat, Libertà.
  - Correction to phase 3 B.4: the top 250 m cell is now **250-53-45 in San Pasquale** (100,0, 0% vegetation, 1,418 residents), not Madonnella (that was before Q49). The demo script doesn't use it.
- `uv run pytest`: 70 passed. `ruff check` is clean, and `npm run build` / `npm run lint` are clean.

### A.3 Deviations from the plan and new decisions

- **Q51**: Render fallback deploy, with a committed data snapshot in `deploy/data/`. It replaces the tar.gz snapshot that was first agreed (one mechanism serves both Render and the clean-start fallback).
- **Q52**: the demo script is in Italian, about 3 minutes. No slides and no recorded video.
- The "clean start < 2 min" check assumes warm package caches. A cold machine also downloads the Python and npm dependencies (not measured; network-bound).
- Technical choices:
  - uvicorn in the demo binds to 127.0.0.1 (ngrok connects locally, so it isn't exposed on the LAN);
  - the uv version is pinned in the Dockerfile to match the local 0.12.20.

### A.4 Process notes

- The questions were asked before building. The user's answer to "extras" introduced Render, which led to a follow-up question on how the data reaches Render.
- The local Docker build failed at first on the user's credential helper (`pass`/gpg), even for public images. The build worked with a temporary empty `DOCKER_CONFIG` (in the scratchpad). The user's Docker config was not changed.
- As in Phase 3, the screenshots found the landscape bug. The automated checks (scroll, console) passed before the fix.

### A.5 Known issues and open points

1. **Real phone over ngrok is not tested** (NFR-10 needs at least one): sheet drag, pinch zoom, portrait and landscape. Safari/iOS is also untested.
2. **The Render deploy is not live yet.** It needs the commit and push, then the Blueprint setup in the Render dashboard. The image was only verified locally.
3. **The snapshot can go stale.** After any `pipeline build`, run `make snapshot` and commit. `scripts/demo.sh` warns when it differs.
4. On a tall, narrow viewport (iPad portrait) the city fits the width and leaves sea above it. This is cosmetic.
5. The image is large (2.19 GB: the full geo stack, including rasterio, which the backend doesn't need). It's fine for Render, but a slimmer runtime dependency group would speed up deploys.

---

## Part B: Handoff for the next agent

### B.1 Read first
1. This file, then `docs/demo_script.md`, and `README.md` (Demo section).
2. `docs/requirements_and_plan.md` §8 (Phase 5 stretch list, §8.1 team split) and §10.0 up to Q52.
3. `CLAUDE.md`.

### B.2 Current state (how to run)
```bash
make demo              # full demo via ngrok (the user's reserved URL)
make demo-local        # http://localhost:8080
make snapshot          # after `uv run python -m pipeline build`, then commit deploy/data/
make docker-build && make docker-run   # the Render image locally
# development is unchanged: uvicorn --reload on :8000 + (cd frontend && npm run dev)
```

### B.3 User steps still open
1. Commit and push. Then in Render: **New → Blueprint** → this repo. Open the Render URL and follow the flow once.
2. Open the ngrok URL on a real phone (mobile network), in portrait and landscape. Try the sheet drag, pinch zoom, a zone card and the simulator.
3. Rehearse `docs/demo_script.md` once with a timer.

### B.4 Implementation notes for what comes next
- The Phase 5 stretch items are in plan §8: weight presets, bus stops (GTFS), Copertino/Lecce. CSV export and NDVI are already done.
- To slim the Docker image, move `rasterio` (and the other pipeline-only packages) into a dependency group and use `uv sync --no-group pipeline` in the Dockerfile. Check first which packages `backend/` imports through `pipeline.model` / `pipeline.sensitivity`.
- Any model change (pipeline or `config/bari.yaml`) → update the methodology (Italian), rebuild, run `make snapshot`, and re-check the numbers in `docs/demo_script.md`.

### B.5 Open questions to ask the user
1. The final product name (Q14) is still open. The UI uses "Urban Green Planner" (Q41).
2. After the team joins: the per-person branches (§8.1).

### B.6 Pitfalls
- Never run git commands other than `git status` / `git diff`.
- The user's Docker credential helper fails without gpg. For local builds, use `DOCKER_CONFIG=<empty dir>`, or have the user unlock `pass`.
- `make demo` refuses to start if port 8080 is busy (e.g. a previous demo still running).
- Don't add `data/processed/` to git; the snapshot in `deploy/data/` is the committed copy (Q51).
