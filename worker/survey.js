// Torque Shed's survey: a Cloudflare Worker (free tier) the game asks to bake the cells of the world nobody has baked
// yet. It holds the one secret the game must not, GITHUB_TOKEN: a fine-grained token that can only run this
// repository's Actions. See worker/README.md for setting it up.
//
//   POST /survey  {"cells": ["577_711", "577_712"]}   (ROW_COLUMN of the 0.25 degree grid, at most MAX_CELLS)
//
// Answers {"status": "baking" | "mapped" | "busy" | "error", "cells": [the ones it set baking], "message": "..."}.
// Cells the index already has are left out; when the bake workflow already has MAX_RUNS runs going it is "busy" (the
// only rate limit, and a free one: GitHub keeps the count). The cells come into index.json as the run finishes, where
// the game looks for them.

const REPO = "Beenster99/torque-shed-world";
const WORKFLOW = "bake.yml";
const INDEX_URL = `https://raw.githubusercontent.com/${REPO}/main/index.json`;
const MAX_CELLS = 16;
const MAX_RUNS = 3;
const CELL_DEG = 0.25;
const ROWS = 180 / CELL_DEG;
const COLUMNS = 360 / CELL_DEG;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") {
      return new Response("Torque Shed survey: POST /survey {\"cells\": [\"ROW_COL\", ...]}\n", {
        headers: { "content-type": "text/plain" },
      });
    }
    if (request.method !== "POST" || url.pathname !== "/survey") {
      return answer(404, "error", [], "There's nothing here.");
    }
    if (!env.GITHUB_TOKEN) {
      return answer(500, "error", [], "The survey has no GitHub token set up.");
    }
    let body;
    try {
      body = await request.json();
    } catch (e) {
      return answer(400, "error", [], "That's not a survey request.");
    }
    const cells = cleanCells(body && body.cells);
    if (cells === null) {
      return answer(400, "error", [], `Ask for 1 to ${MAX_CELLS} cells, each ROW_COLUMN.`);
    }
    return survey(cells, env, fetch);
  },
};

// The cells asked for, made safe (unique, in range), or null when they aren't cells.
export function cleanCells(raw) {
  if (!Array.isArray(raw) || raw.length < 1 || raw.length > MAX_CELLS) {
    return null;
  }
  const out = [];
  for (const c of raw) {
    const m = /^(\d{1,3})_(\d{1,4})$/.exec(String(c));
    if (!m) {
      return null;
    }
    const row = Number(m[1]);
    const col = Number(m[2]);
    if (row >= ROWS || col >= COLUMNS) {
      return null;
    }
    const key = `${row}_${col}`;
    if (!out.includes(key)) {
      out.push(key);
    }
  }
  return out;
}

// "LAT,LON" of the middle of cell "ROW_COL", as the bake workflow takes a point.
export function cellPoint(key) {
  const [row, col] = key.split("_").map(Number);
  const lat = (row + 0.5) * CELL_DEG - 90;
  const lon = (col + 0.5) * CELL_DEG - 180;
  return `${lat.toFixed(3)},${lon.toFixed(3)}`;
}

// Sets `cells` baking unless the index has them or the workflow is busy. `fetcher` is fetch (the tests pass their own).
export async function survey(cells, env, fetcher) {
  const github = {
    authorization: `Bearer ${env.GITHUB_TOKEN}`,
    accept: "application/vnd.github+json",
    "user-agent": "torque-shed-survey",
    "x-github-api-version": "2022-11-28",
  };
  const idx = await fetcher(INDEX_URL, { headers: { "user-agent": "torque-shed-survey" } });
  if (!idx.ok) {
    return answer(502, "error", [], "Couldn't read the world's index.");
  }
  const index = await idx.json();
  const known = (index && index.cells) || {};
  const wanted = cells.filter((c) => !(c in known));
  if (wanted.length === 0) {
    return answer(200, "mapped", [], "Those roads are mapped already.");
  }
  let going = 0;
  for (const status of ["queued", "in_progress"]) {
    const runs = await fetcher(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?status=${status}&per_page=1`,
      { headers: github },
    );
    if (!runs.ok) {
      return answer(502, "error", [], `Couldn't ask GitHub how busy it is (${runs.status}).`);
    }
    going += Number((await runs.json()).total_count || 0);
  }
  if (going >= MAX_RUNS) {
    return answer(429, "busy", [], "The surveyors are busy: try again in a few minutes.");
  }
  const run = await fetcher(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { ...github, "content-type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { cells: wanted.map(cellPoint).join(" "), tools_ref: "main" } }),
  });
  if (run.status !== 204) {
    return answer(502, "error", [], `GitHub wouldn't start the survey (${run.status}).`);
  }
  return answer(202, "baking", wanted, `Surveying ${wanted.length} cell${wanted.length === 1 ? "" : "s"}: about ten minutes.`);
}

function answer(code, status, cells, message) {
  return new Response(JSON.stringify({ status, cells, message }), {
    status: code,
    headers: { "content-type": "application/json" },
  });
}
