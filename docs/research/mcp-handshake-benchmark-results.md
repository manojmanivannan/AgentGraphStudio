# MCP Per-Run Connection Handshake Cost — Measured Results

> Research note answering GitHub issue #127 (companion to
> [mcp-streamable-http-transport.md](./mcp-streamable-http-transport.md), which establishes
> the wire facts; the handshake shape benchmarked here is the legacy 2025-03-26..2025-11-25
> Streamable HTTP sequence that every real deployed server speaks today:
> TCP(+TLS) → POST `initialize` → POST `notifications/initialized` (202) → POST
> `tools/list`). Decision #120 lands **per-run sessions** (one connection opened at run
> setup, reused for all of that run's tool calls); #127 asks whether that per-run open
> cost is acceptable, or whether the fallbacks (per-tool-call sessions, pooled long-lived
> sessions) must be exercised.
>
> **All numbers below were measured on 2026-10-11** with the kept, reproducible script
> [mcp-handshake-benchmark.py](./mcp-handshake-benchmark.py) (runs committed alongside
> this note; raw console output reproduced in the tables). Nothing in any primary source
> publishes a wall-clock figure for the Streamable HTTP handshake — #118's survey noted
> this — so these numbers are the primary evidence.

---

## Verdict (the sentence the spec needs)

**Per-run connection opening is acceptable and the fallbacks should not be exercised as
general mechanisms: the full legacy handshake costs 2 ms (localhost) — 0.35–0.92 s
(p50) against real distant public servers (~82–150 ms RTT, TLS included), i.e. under one
second once per run, versus LLM call latencies of 2–30+ s per DSPy iteration that already
dominate every agent run.** Per-tool-call sessions are measurably harmful, not merely
unnecessary: at 10 tool calls/run they add **4.5 s (p50, 82 ms-RTT server) to 8.2 s
(p50, 150 ms-RTT server)** of pure handshake overhead per run — the same order as one
LLM call — while per-run pays that cost once. Pooled long-lived sessions in the
BackgroundRunWorker buy back at most ~1 s per run while re-introducing the stale-session
404 / re-initialize machinery; the only scenario where they'd matter — a canvas mounting
several distant servers, e.g. 5+ servers at ≥150 ms RTT ≈ 4.5 s+ aggregate open cost —
is better handled by opening the per-run connections concurrently at run setup (a
client-side change that keeps #120's model intact) than by pooling.

Numbers behind that verdict are in [The derived comparison](#the-derived-comparison-per-run-vs-per-tool-call);
the one-sentence rule of thumb is in [Scaling rule](#scaling-rule).

---

## Methodology

**Script.** `docs/research/mcp-handshake-benchmark.py`, stdlib-only, hand-rolled
HTTP/1.1-over-one-TLS-connection client. Deliberately not using the `mcp` SDK (it is not
installed in `backend/` and the ticket forbids touching its lockfiles): the script speaks
the legacy wire shape directly from the spec — `Accept: application/json,
text/event-stream`, `MCP-Protocol-Version` after initialize, `MCP-Session-Id` echoed when
issued — and **times each phase separately on the same connection**:

1. TCP connect (DNS resolved once up front, outside the timed loop; IPv4 forced for
   determinism),
2. TLS 1.3 handshake,
3. POST `initialize` (result parsed from `application/json` or SSE `data:` lines),
4. POST `notifications/initialized` (expects 202),
5. POST `tools/list`,
6. warm POST `tools/call` (a real, cheap tool on the already-open session), and
7. a warm repeat of `tools/list` — zero per-server work everywhere tested, so its
   round-trip is the **pure transport RTT floor** used to separate RTT from handshake
   cost.

Each "open" starts from a fresh connection (fresh TCP, fresh TLS, fresh session),
exactly modeling a fresh per-run SDK client (`streamable_http_client` per `async with`).
Nearest-rank p50/p95 over **n=25 handshakes per server** for the headline run, plus a
second independent **n=15** pass on all servers to quantify run-to-run stability; a
warm-up open is executed but not counted (DNS, TLS session cache, server cold path).
Percentiles are from sorted values; with n=25 the nearest-rank p95 is effectively the
2nd-largest sample.

**Servers.**

| Label | URL | Backend (from responses) | Session id issued | Notes |
|---|---|---|---|---|
| `local` | `http://127.0.0.1:8123/mcp` | FastMCP 4.1.0 reference server written for this benchmark (embedded `serve-local` subcommand; run in a throwaway uv venv `/tmp`, uvicorn) | yes | zero-NAT floor; tool `add(a,b)` |
| `deepwiki` | `https://mcp.deepwiki.com/mcp` | uvicorn (`server: uvicorn`), `serverInfo` DeepWiki 2.14.3 | no (stateless) | distant (~150 ms RTT) |
| `context7` | `https://mcp.context7.com/mcp` | Express (`x-powered-by`), serverInfo Context7 4.3.0 | no (stateless) | mid (~82 ms RTT) |
| `learn` | `https://learn.microsoft.com/api/mcp` | ASP.NET behind Akamai | **yes** (opaque base64 id) | TCP RTT to edge only 3 ms, but every POST costs ~100 ms+ to origin |

- Verification: each candidate got a single anonymous `initialize` POST before
  benchmarking and had to answer with a JSON-RPC `result` (SSE or JSON accepted). All
  four passed and all four negotiated `protocolVersion: "2025-11-25"`.
- **Candidate URL corrections:** the ticket's `https://mcp.deepwiki.com/http` returns
  **404**; the live endpoint is `/mcp` (their `/sse` legacy endpoint returns **410 Gone**,
  consistent with the deprecated HTTP+SSE transport). No candidate failed on auth: all
  three public servers accept anonymous initialize + tools/list.
- Warm-call tools used (all verified to return non-`isError` content before the run):
  deepwiki `read_wiki_structure {"repoName":"microsoft/vscode"}`; context7
  `resolve-library-id {"query":"react","libraryName":"react"}` (context7 validates **both**
  fields; two earlier passes with one field each returned `isError:true` and were
  discarded — their timings were still recorded in the console log but are not the basis
  of any number below); learn `microsoft_docs_search {"query":"asyncio gather timeout"}`.
- **Client network:** UK residential fibre (toob/AS60377, Southampton, GB), one vantage
  point, one time of day (11:20–11:35 UTC). See Threats to validity.
- TLS: `ssl.create_default_context` + system CA bundle. Notable environment quirk the
  script builds around: uv-managed CPython on this machine has no default OpenSSL verify
  path for `mcp.context7.com` ("unable to get local issuer certificate"), so the script
  loads `/etc/ssl/certs/ca-certificates.crt` explicitly (`load_tls_context()`).

---

## Results (2026-10-11, n=25 per server)

Times in ms, nearest-rank percentiles. `open` = TCP+TLS + initialize + initialized +
tools/list = the entire per-run session cost.

### local (FastMCP 4.1.0, 127.0.0.1:8123)

| metric | p50 | p95 | min | max |
|---|---|---|---|---|
| tcp | 0.0 | 0.1 | 0.0 | 0.1 |
| tls | 0.0 | 0.0 | 0.0 | 0.0 |
| initialize | 0.9 | 1.1 | 0.8 | 1.2 |
| initialized | 0.2 | 0.3 | 0.2 | 0.3 |
| tools/list | 0.8 | 1.1 | 0.8 | 1.1 |
| **open (total)** | **2.1** | **2.3** | **1.9** | **2.3** |

warm `tools/call` (`add`): p50 **0.9**, p95 1.0 · warm transport RTT (repeat tools/list):
p50 0.8 · 25/25 opens OK, 0 reconnects.

### deepwiki (mcp.deepwiki.com, ~150 ms RTT)

| metric | p50 | p95 | min | max |
|---|---|---|---|---|
| tcp | 149.0 | 151.7 | 145.3 | 151.8 |
| tls | 157.4 | 160.0 | 152.8 | 160.2 |
| initialize | 299.9 | 304.0 | 290.7 | 304.7 |
| initialized | 150.2 | 152.5 | 146.0 | 153.7 |
| tools/list | 152.9 | 154.8 | 147.9 | 840.9 |
| **open (total)** | **910.4** | **923.9** | **882.9** | **1599.2** |

warm `tools/call` (`read_wiki_structure`): p50 **264.7**, p95 280.5 · warm transport RTT:
p50 152.4 · 25/25 opens OK. One outlier sample (tools/list 841 ms → open 1599 ms).

### context7 (mcp.context7.com, ~82 ms RTT)

| metric | p50 | p95 | min | max |
|---|---|---|---|---|
| tcp | 82.0 | 83.5 | 80.0 | 83.9 |
| tls | 90.3 | 91.3 | 88.3 | 92.5 |
| initialize | 163.0 | 165.9 | 159.6 | 167.2 |
| initialized | 82.1 | 83.9 | 80.9 | 84.5 |
| tools/list | 82.8 | 84.1 | 80.9 | 84.4 |
| **open (total)** | **500.1** | **508.4** | **489.7** | **512.5** |

warm `tools/call` (`resolve-library-id`, valid): p50 **1164.9**, p95 1508.1 — server-side
search work, *not* transport · warm transport RTT: p50 82.8 · 25/25 opens OK.

### learn (learn.microsoft.com, 3 ms edge RTT, ~110 ms origin per POST)

| metric | p50 | p95 | min | max |
|---|---|---|---|---|
| tcp | 2.8 | 4.0 | 2.3 | 4.7 |
| tls | 12.4 | 14.8 | 11.7 | 49.3 |
| initialize | 108.7 | 152.8 | 98.8 | 170.3 |
| initialized | 108.2 | 174.5 | 96.0 | 193.5 |
| tools/list | 103.1 | 158.8 | 97.0 | 167.0 |
| **open (total)** | **350.5** | **445.4** | **310.0** | **509.4** |

warm `tools/call` (`microsoft_docs_search`): p50 **417.6**, p95 794.4 — origin search
work · warm transport RTT: p50 114.2, p95 161.6 · 25/25 opens OK. This server is the
jitteriest (independent n=15 pass: open p50 434.1, **p95 683.2**).

### Run-to-run stability (independent second pass, n=15, all servers)

| metric (p50) | pass 1 (n=25) | pass 2 (n=15) |
|---|---|---|
| local open | 2.1 | 2.2 |
| deepwiki open | 910.4 | 913.5 |
| context7 open | 500.1 | 496.6 |
| learn open | 350.5 | 434.1 |

deepwiki and context7 repeat within ~1 %. learn varies ~24 % at p50 (and p95 445 → 683):
its cost is origin processing behind a UK Akamai edge, which queues. Treat all "learn"
numbers as order-of-magnitude for CDNeed servers rather than a stable constant.

### Phase attribution

- TCP ≈ 1 RTT; TLS ≈ 1 RTT + crypto (deepwiki 149+157 ms). TLS is where a distant
  server hurts most *on connect only*; it is paid once per session, not per request.
- One HTTP POST round-trip ≈ 1 RTT for the stateless servers (initialized & tools/list
  are almost exactly 1×RTT on deepwiki/context7). `initialize` costs ~2×RTT+work
  (deepwiki 300 ms = 149×2) — likely first-request server work (session minting /
  upstream setup), not wire shape.
- learn shows a different regime: 3 ms to the edge but **every** POST costs ~100 ms
  because it proxies to the Azure origin. At a CDN-fronted server, RTT to the edge does
  not predict handshake cost; origin round-trips do.
- The stateless servers (deepwiki, context7) issued **no** `MCP-Session-Id` — their
  behavior is already compatible with the 2026-07-28 revision, where the handshake
  disappears entirely and per-run cost collapses to TCP+TLS+one POST (~0.6 s at 150 ms
  RTT, ~2 ms local).

---

## The derived comparison: per-run vs per-tool-call

Basis: p50 numbers from the headline run — except context7, whose row uses its
corrected warm-call pass throughout (`H = 498.9`, since the headline run's warm call
was the discarded wrong-argument one). `H` = per-open handshake total; `c` = warm
per-call cost on the open session (warm `tools/call` p50 where measured; for the
transport-only comparisons, the warm RTT floor 0.8 / 82.8 / 152.4 / 114.2 ms).

- **per-run (decision #120):** `H + k·c` — the handshake once, then k warm calls.
- **per-tool-call (fallback):** `k·(H + c)` — a full fresh handshake before *every* call.
- **extra overhead of per-tool-call over per-run:** `(k−1)·H` — i.e. the fallback's harm
  scales only with H and k, independent of what tools do.

| server | H (p50) | c (p50) | per-run, k=3 | per-tool-call, k=3 | overhead k=3 | per-run, k=10 | per-tool-call, k=10 | overhead k=10 |
|---|---|---|---|---|---|---|---|---|
| local | 2.1 | 0.9 | 4.9 ms | 9.1 ms | +4.2 ms | 11.4 ms | 30.4 ms | +19.1 ms |
| deepwiki | 910.4 | 264.7 | 1704 ms | 3525 ms | **+1821 ms** | 3557 ms | 11750 ms | **+8194 ms** |
| context7 | 498.9 | 1164.9 | 3994 ms | 4991 ms | +998 ms | 12148 ms | 16638 ms | **+4490 ms** |
| learn | 350.5 | 417.6 | 1603 ms | 2304 ms | +701 ms | 4527 ms | 7681 ms | **+3154 ms** |

Arithmetic shown explicitly for deepwiki, k=10: per-run = 910.4 + 10×264.7 = 3557 ms;
per-tool-call = 10×(910.4+264.7) ≈ 11750 ms; overhead = 9×910.4 ≈ 8194 ms (the script
prints the unrounded values the table contains).

Read with the per-call basis in mind: context7 and learn's warm calls include
server-side work (search backends), so their *absolute* run totals are dominated by the
tools themselves — but the **handshake overhead column is precisely the marginal cost of
the per-tool-call fallback**, and it is what #120's fallback decision is about. Even the
best real-world case (learn, 350 ms open) pays **+3.2 s per 10-tool-call run** if you
degrade to per-tool-call — more than one full LLM round-trip. Against typical run
shapes, that fallback is never the right steady state; it is only defensible as the
retry-then-degrade path #120 already specifies (i.e. pay it once on failure rather than
fail the run).

Scaling rule: for well-behaved (non-CDN-fronted) servers, **H ≈ 6×RTT** (deepwiki
6.10×149 ms; context7 6.09×82 ms; local consistent) — TCP + TLS + initialize(2) +
initialized + tools/list. CDN-fronted servers behave like H ≈ (per-POST origin cost)×3
+tiny, which the client cannot see from RTT.

---

## Verdict detail vs scenarios

- **Interactive agent runs (typical canvas, 1–2 MCP servers):** per-run open is 2 ms
  (local/nearby) to 0.9 s p50 / 0.92 s p95 (worst measured: distant 150 ms-RTT server).
  A single StreamingReAct iteration is seconds; opening the MCP session is 1–10 % of
  *one* LLM call, well under 5 % of a realistic multi-call run. **Keep per-run sessions
  as the only mechanism; the spec does not need to exercise per-tool-call or pooled
  sessions.**
- **Per-tool-call sessions:** quantified above — +0.7 s to +8.2 s pure overhead per run
  at 10 calls. Do not adopt as steady state; keep only as #120's degrade-on-retry path.
- **Pooled long-lived sessions (BackgroundRunWorker):** the maximum they can save is one
  handshake per run (≤0.92 s p50 measured), while adding the stale-session 404 /
  re-initialize machinery that per-run sessions exist to avoid (see
  mcp-streamable-http-transport.md §5: SDKs do *not* auto-reinitialize on 404). Not
  worth it at any measured RTT.
- **Many MCP servers per canvas:** per-run open cost is additive across servers. At
  ~0.9 s per distant server, canvases mounting **≥5 distant (~150 ms RTT) servers** pay
  ≥4.5 s at setup. Threshold guidance: if a canvas mounts >2 servers with RTT ≥150 ms
  (H ≥ 0.9 s each), the spec should direct implementations to **open the per-run
  connections concurrently** at run setup (bounded by the slowest single open, not the
  sum). This preserves #120's per-run model; no pooling or per-tool-call fallback needed.
- **2026-07-28 "modern" servers** (stateless, no session ids — deepwiki and context7
  already behave this way): no `initialize` handshake at all, so per-run open tends to
  TCP+TLS+one POST. The per-run design gets *cheaper* as the ecosystem migrates. The
  same script applies with `PROTOCOL_VERSION = "2026-07-28"` once a modern-only server
  is available; nothing about the verdict changes in that direction.

## Threats to validity

1. **One geography, one vantage point, one time of day.** All measurements from a UK
   residential connection (Southampton, GB), 2026-10-11 ~11:20–11:35 UTC. Absolute
   numbers transfer as RTT-scaling (the ≈6×RTT rule), not as constants. No trans-pacific
   or intra-datacenter-hosted-public-server data point was available; deepwiki
   (~150 ms RTT from UK) is the distant case, but a hypothetical ≥300 ms-RTT server
   would have H ≈ 1.8 s + origin work — still within the verdict, but worth re-measuring
   if the product targets such regions.
2. **Learn-median jitter.** The Akamai/origin-pathed server shifted p50 by +24 % between
   passes 25 minutes apart. Any single-pass number for CDN-fronted, origin-proxied
   servers is unstable; the honest bound for learn is "0.35–0.7 s open, p50". No such
   instability was observed for the two stateless servers or localhost.
3. **Warm `tools/call` costs are not transport measurements.** deepwiki
   (264.7 ms), context7 (1164.9 ms) and learn (417.6 ms) warm calls include real
   server-side backend work; their handshake/call ratios are therefore not
   transport-pure. The clean transport figures are localhost (0.9 ms) and the warm
   `tools/list` RTT rows. This does not affect the per-tool-call overhead column, which
   depends only on H.
4. **Server warm-up.** Each measurement excludes a warm-up open, but public servers may
   have been cache-hot (deepwiki's `read_wiki_structure`, context7's resolver) in ways a
   fresh production deployment would not be. `initialize` on deepwiki costing 2×RTT may
   partly reflect upstream-cold work; re-runs after warm-up showed no decay, so it is
   treated as recurring, not just cold-start.
5. **Client-side precision.** Hand-rolled client, sequential loop, `time.perf_counter()`,
   DNS pre-resolved, IPv4 forced, keep-alive reused; zero mid-handshake reconnects and
   zero failures across 40 opens/server. Measurement overhead per phase is ~µs and
   negligible at the ms scale. TLS session resumption was not controlled (new
   `SSLContext` per connection, OS session cache state unspecified); the SDK's pooled
   httpx client behaves similarly per fresh client, but a long-lived pooled client could
   resume TLS and shave ~1 RTT off pooled-mode connects — one more reason pooling
   doesn't help.
6. **n=25.** Nearest-rank p95 over 25 samples is the ~2nd-largest value; tails are
   indicative only. The n=15 stability pass partially compensates.
7. **Two `context7` warm-call discard passes.** The first context7 runs used wrong
   arguments and returned `isError:true` fast (≈RTT). Those numbers were not used for
   anything except the corrected re-run shown above. Documented because it changed the
   warm-call figure from 82.9 ms (no server work) to 1164.9 ms (real work).
8. **Local server is FastMCP 4.1.0**, not the exact stacks of the public servers; its
   value here is only as the zero-RTT floor, which is stack-independent.

## Reproducing

```bash
# local reference server (throwaway venv with fastmcp)
uv venv /tmp/mcpbench-venv && VIRTUAL_ENV=/tmp/mcpbench-venv uv pip install fastmcp
VIRTUAL_ENV=/tmp/mcpbench-venv /tmp/mcpbench-venv/bin/python \
  docs/research/mcp-handshake-benchmark.py serve-local --port 8123 &

# benchmark (repeatable --url; label-scoped warm tool)
uv run python docs/research/mcp-handshake-benchmark.py \
  --url 'local=http://127.0.0.1:8123/mcp' \
  --call-tool 'local=add' --call-args 'local={"a": 2, "b": 3}' \
  --url 'deepwiki=https://mcp.deepwiki.com/mcp' \
  --call-tool 'deepwiki=read_wiki_structure' --call-args 'deepwiki={"repoName": "microsoft/vscode"}' \
  --url 'context7=https://mcp.context7.com/mcp' \
  --call-tool 'context7=resolve-library-id' --call-args 'context7={"query": "react", "libraryName": "react"}' \
  --url 'learn=https://learn.microsoft.com/api/mcp' \
  --call-tool 'learn=microsoft_docs_search' --call-args 'learn={"query": "asyncio gather timeout"}' \
  --runs 25 --timeout 30
```

## Sources

- Wire facts and handshake shape: [mcp-streamable-http-transport.md](./mcp-streamable-http-transport.md)
  (§1.1 legacy transports, §5 per-run connection practice), which cites
  [2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
  and [2026-07-28 streamable-http](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http).
- All latency numbers in this document: produced by
  [mcp-handshake-benchmark.py](./mcp-handshake-benchmark.py) on the hosts and dates
  stated in Methodology.
- Servers: mcp.deepwiki.com, mcp.context7.com, learn.microsoft.com/api/mcp (verified
  live 2026-10-11), local FastMCP 4.1.0 reference server.