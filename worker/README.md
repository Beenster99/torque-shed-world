# The survey worker

When a crew presses **Survey** on the Route planner TV where nobody has mapped the roads yet, the game asks this
Cloudflare Worker to bake those cells. The worker holds the one secret the game must not: a GitHub token that can only
run this repository's Actions. It leaves out cells the index already has, and says "busy" while three bake runs are
going (that is its only rate limit, and it costs nothing). Cloudflare's free plan is plenty: nothing here is paid for.

## Setting it up (once)

1. **The token.** On GitHub: Settings, Developer settings, Personal access tokens, **Fine-grained tokens**, Generate new
   token. Repository access: **Only select repositories**, `Beenster99/torque-shed-world`. Permissions: **Actions: Read
   and write** (nothing else). Copy it; don't paste it anywhere but step 3.
2. **The worker.** In the Cloudflare dashboard: Workers & Pages, Create, **Create Worker**, name it
   `torque-shed-survey`, Deploy. Then **Edit code**, select everything in the editor, paste in the whole of
   `worker/survey.js` from this repository, and **Deploy**.
3. **The secret.** On the worker's page: Settings, **Variables and Secrets**, Add. Type **Secret**, name
   `GITHUB_TOKEN`, value the token from step 1. Deploy.
4. **Check it.** Open <https://torque-shed-survey.simonbennett3.workers.dev/> in a browser: it should say
   "Torque Shed survey: POST /survey ...".

The game asks `https://torque-shed-survey.simonbennett3.workers.dev/survey`. If the worker is called something else,
the game's `Survey.URL` (scripts/survey.gd) must say so.

## What it does

`POST /survey` with `{"cells": ["577_711", ...]}` (at most 16 cells of the 0.25 degree grid, ROW_COLUMN) answers
`{"status": "baking" | "mapped" | "busy" | "error", "cells": [...], "message": "..."}`. Baking runs the **Bake cells**
workflow with the middles of the cells; they come into `index.json` when the run finishes, ten minutes or so later.

Tests (Node 18 or later, no installs): `node --test worker/survey.test.mjs`.

If the token is ever leaked, delete it on GitHub (step 1's page) and make another: it can only run this repository's
bake workflow, and the worker is the only thing that has it.
