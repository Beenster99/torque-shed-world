// Tests for the survey worker, with a stand-in for GitHub: node --test worker/survey.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import worker, { cellPoint, cleanCells, survey } from "./survey.js";

// A stand-in for GitHub: the index has `baked`, the workflow has `going` runs, and what was asked is kept.
function github({ baked = {}, going = 0, dispatch = 204, index = 200 } = {}) {
  const asked = [];
  const fetcher = async (url, init = {}) => {
    asked.push({ url, init });
    if (url.endsWith("/index.json")) {
      return new Response(JSON.stringify({ format: 1, cells: baked }), { status: index });
    }
    if (url.includes("/runs?status=")) {
      return new Response(JSON.stringify({ total_count: url.includes("queued") ? going : 0 }), { status: 200 });
    }
    if (url.endsWith("/dispatches")) {
      return new Response(null, { status: dispatch });
    }
    return new Response("?", { status: 404 });
  };
  return { fetcher, asked };
}

const env = { GITHUB_TOKEN: "test-token" };

test("cells are checked and made unique", () => {
  assert.deepEqual(cleanCells(["577_711", "577_711", "577_712"]), ["577_711", "577_712"]);
  assert.equal(cleanCells([]), null);
  assert.equal(cleanCells("577_711"), null);
  assert.equal(cleanCells(["720_0"]), null);
  assert.equal(cleanCells(["1_1440"]), null);
  assert.equal(cleanCells(["5x_1"]), null);
  assert.equal(cleanCells(Array.from({ length: 17 }, (_, i) => `500_${i}`)), null);
});

test("a cell's middle is the point the bake workflow takes", () => {
  assert.equal(cellPoint("577_711"), "54.375,-2.125");
  assert.equal(cellPoint("0_0"), "-89.875,-179.875");
});

test("cells nobody has baked are set baking, the rest left out", async () => {
  const gh = github({ baked: { "577_711": { hash: "x" }, "577_712": { empty: true } } });
  const res = await survey(["577_711", "577_712", "577_713"], env, gh.fetcher);
  const out = await res.json();
  assert.equal(res.status, 202);
  assert.equal(out.status, "baking");
  assert.deepEqual(out.cells, ["577_713"]);
  const sent = gh.asked.find((a) => a.url.endsWith("/dispatches"));
  assert.ok(sent);
  assert.equal(sent.init.headers.authorization, "Bearer test-token");
  assert.deepEqual(JSON.parse(sent.init.body), { ref: "main", inputs: { cells: "54.375,-1.625", tools_ref: "main" } });
});

test("mapped already, nothing is baked", async () => {
  const gh = github({ baked: { "577_711": { hash: "x" } } });
  const out = await (await survey(["577_711"], env, gh.fetcher)).json();
  assert.equal(out.status, "mapped");
  assert.ok(!gh.asked.some((a) => a.url.endsWith("/dispatches")));
});

test("busy surveyors: nothing more is started", async () => {
  const gh = github({ going: 3 });
  const res = await survey(["100_100"], env, gh.fetcher);
  assert.equal(res.status, 429);
  assert.equal((await res.json()).status, "busy");
  assert.ok(!gh.asked.some((a) => a.url.endsWith("/dispatches")));
});

test("GitHub saying no is an error, not a survey", async () => {
  const res = await survey(["100_100"], env, github({ dispatch: 403 }).fetcher);
  assert.equal(res.status, 502);
  assert.equal((await res.json()).status, "error");
});

test("the worker turns away anything but a survey, and needs its token", async () => {
  const get = await worker.fetch(new Request("https://x.workers.dev/"), env);
  assert.equal(get.status, 200);
  const wrong = await worker.fetch(new Request("https://x.workers.dev/other", { method: "POST" }), env);
  assert.equal(wrong.status, 404);
  const junk = await worker.fetch(new Request("https://x.workers.dev/survey", { method: "POST", body: "nope" }), env);
  assert.equal(junk.status, 400);
  const bad = await worker.fetch(
    new Request("https://x.workers.dev/survey", { method: "POST", body: JSON.stringify({ cells: ["no"] }) }), env);
  assert.equal(bad.status, 400);
  const untokened = await worker.fetch(
    new Request("https://x.workers.dev/survey", { method: "POST", body: JSON.stringify({ cells: ["1_1"] }) }), {});
  assert.equal(untokened.status, 500);
});
