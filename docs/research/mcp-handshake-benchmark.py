#!/usr/bin/env python3
"""Benchmark MCP Streamable HTTP per-run connection handshake cost.

Measures, separately, the wall-clock cost of the phases that make up one
Streamable HTTP "session open" against a real server:

    TCP connect -> TLS handshake -> POST initialize -> POST notifications/initialized
    -> POST tools/list -> (warm) POST tools/call

This mirrors what the official `mcp` SDK's `streamable_http_client` does per
`async with` block (legacy 2025-03-26..2025-11-25 wire shape). The HTTP client
is a minimal, stdlib-only HTTP/1.1 implementation written by hand on purpose:
it measures the *transport*, not SDK internals, and lets every phase be timed
individually on a single TLS connection.

Two modes are quantified from these primitives:

  per-run        : 1 handshake per run, then k warm tool calls on the same
                   connection (what decision #120 specifies).
  per-tool-call  : a full handshake before EVERY tool call = k * handshake
                   total, plus k warm calls. Derived arithmetically and also
                   printable via --derive-k.

Usage:
  # benchmark one or more servers (repeatable --url, per-label call tool/args)
  python mcp-handshake-benchmark.py \
      --url local=http://127.0.0.1:8123/mcp \
      --url deepwiki=https://mcp.deepwiki.com/mcp \
      --call-tool 'local={"name":"add"}' ...

  # with label-scoped tool invocation for the warm-call measurement:
  --call-tool 'LABEL=TOOL_NAME' --call-args 'LABEL={"json":"args"}'

  # spin up the local reference server (needs fastmcp in the env):
  python mcp-handshake-benchmark.py serve-local --port 8123

Stdlib only (benchmark side). For `serve-local`, fastmcp>=2 must be installed
(checked dynamically); everything else works with plain python3.
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit

PROTOCOL_VERSION = "2025-11-25"  # what real deployed servers speak today
CLIENT_INFO = {"name": "ags-handshake-bench", "version": "0.0.1"}

_CA_BUNDLE_CANDIDATES = (
    # uv/pyenv-managed interpreters often build ssl with no default verify
    # paths, so fall back to the common system bundle locations explicitly
    "/etc/ssl/certs/ca-certificates.crt",          # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",            # Fedora/RHEL
    "/etc/ssl/ca-bundle.pem",
    "/usr/local/share/certs/ca-root-nss.crt",      # FreeBSD
    "/etc/openssl/certs/cert.pem",                 # macOS (homebrew openssl)
)


def load_tls_context() -> ssl.SSLContext:
    import os

    env_ca = os.environ.get("SSL_CERT_FILE")
    candidates = ([env_ca] if env_ca else []) + list(_CA_BUNDLE_CANDIDATES)
    for ca in candidates:
        if ca and os.path.isfile(ca):
            return ssl.create_default_context(cafile=ca)
    return ssl.create_default_context()


# --------------------------------------------------------------------------
# Minimal HTTP/1.1 client over one TCP(+TLS) connection, with per-phase timers
# --------------------------------------------------------------------------


class ConnectTimings:
    tcp: float = 0.0
    tls: float = 0.0


class Http1Client:
    """One connection, several sequential POSTs, each phase timed separately.

    Deliberately hand-rolled: httpx/http-client do not let us attribute time to
    TCP vs TLS vs individual requests on a pooled connection without hooks, and
    we want the transport cost (not SDK internals) measured per phase.
    """

    def __init__(self, url: str, timeout: float = 15.0):
        u = urlsplit(url)
        if not u.hostname:
            raise ValueError(f"unparseable url: {url}")
        self.scheme = u.scheme or "https"
        self.host = u.hostname
        self.port = u.port or (443 if self.scheme == "https" else 80)
        self.target = u.path or "/"
        if u.query:
            self.target += "?" + u.query
        self.hostname_header = self.host if ":" not in self.host else f"[{self.host}]"
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.session_id: str | None = None
        self.reconnects = 0
        self._addr = None  # resolved once, outside timed loops
        self._pending = b""  # bytes read past the current response (pipelining)

    # ---- connection ----

    def resolve(self):
        infos = socket.getaddrinfo(
            self.host, self.port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        # prefer IPv4 for run-to-run determinism (IPv6 happy-eyeballs jitter);
        # fall back to the first result if the host is IPv6-only
        v4 = [i for i in infos if i[0] == socket.AF_INET]
        self._addr = (v4 or infos)[0][4][:2]

    def _raw_connect(self) -> ConnectTimings:
        t = ConnectTimings()
        t0 = time.perf_counter()
        raw = socket.create_connection(self._addr, timeout=self.timeout)
        t1 = time.perf_counter()
        t.tcp = t1 - t0
        if self.scheme == "https":
            self.sock = load_tls_context().wrap_socket(raw, server_hostname=self.host)
            t.tls = time.perf_counter() - t1
        else:
            self.sock = raw
        self.sock.settimeout(self.timeout)
        return t

    def connect(self) -> ConnectTimings:
        if self._addr is None:
            self.resolve()
        timings = self._raw_connect()
        return timings

    def _ensure_open(self) -> ConnectTimings:
        """Transparently reconnect if the server closed us after the last SSE."""
        if self.sock is None:
            self.reconnects += 1
            return self.connect()
        return ConnectTimings()

    # ---- wire ----

    def _post(self, payload: dict | None, headers_extra: dict | None = None):
        """Returns (status, headers, body_bytes). Reconnects transparently."""
        self._ensure_open()
        headers = {
            "Host": f"{self.hostname_header}"
            + ("" if self.port in (80, 443) else f":{self.port}"),
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "User-Agent": "mcp-handshake-benchmark/1.0",
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        if headers_extra:
            headers.update(headers_extra)
        body = b"" if payload is None else json.dumps(payload).encode()
        if payload is not None:
            headers["Content-Length"] = str(len(body))
        head = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        wire = f"POST {self.target} HTTP/1.1\r\n{head}\r\n".encode()
        if payload is not None:
            wire += body
        self.sock.sendall(wire)
        return self._read_response()

    def _read_response(self):
        buf = self._pending
        self._pending = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("EOF while reading response headers")
            buf += chunk
        head, _, body = buf.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        parts = lines[0].split(None, 2)
        status = int(parts[1])
        headers = {}
        for line in lines[1:]:
            k, _, v = line.partition(b":")
            headers[k.strip().lower().decode()] = v.strip().decode()

        te = headers.get("transfer-encoding", "").lower()
        if "chunked" in te:
            body = self._read_chunked(body)
            framing = "chunked"
        elif "content-length" in headers:
            n = int(headers["content-length"])
            while len(body) < n:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                body += chunk
            body = body[:n]
            framing = "content-length"
        else:
            # no framing: response ends at connection close
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                body += chunk
            self.sock_state = "closed"
            framing = "until-close"
        keep_alive = "close" not in headers.get("connection", "").lower()
        self.sock_state = "open" if keep_alive and framing != "until-close" else "closed"
        if self._pending and framing == "chunked":
            pass  # leftover bytes (should not happen for MCP) are kept for reuse
        if self.sock_state == "closed":
            self.close()
        return status, headers, body

    def _read_chunked(self, buf: bytes) -> bytes:
        out = b""
        while True:
            while b"\r\n" not in buf:
                buf += self.sock.recv(65536)
            line, _, buf = buf.partition(b"\r\n")
            size = int(line.split(b";")[0], 16)
            if size == 0:
                break
            need = size + 2  # data + trailing CRLF
            while len(buf) < need:
                buf += self.sock.recv(65536)
            out += buf[:size]
            buf = buf[need:]
        # trailing CRLF (or trailers before the final CRLF pair)
        if buf.startswith(b"\r\n"):
            buf = buf[2:]
        elif buf:
            while b"\r\n\r\n" not in buf:
                buf += self.sock.recv(65536)
            buf = buf.partition(b"\r\n\r\n")[2]
        self._pending = buf
        return out

    # ---- MCP phases ----

    @staticmethod
    def _extract_json(body: bytes, content_type: str, request_id: int):
        """application/json body or SSE stream -> the JSON-RPC response."""
        if "text/event-stream" in content_type:
            for line in body.decode("utf-8", "replace").splitlines():
                if line.startswith("data:"):
                    payload = line[len("data:") :].strip()
                    if not payload:
                        continue
                    try:
                        msg = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("id") == request_id and ("result" in msg or "error" in msg):
                        return msg
            return None
        return json.loads(body.decode("utf-8"))

    def initialize(self, request_id: int) -> tuple[float, dict]:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        }
        t0 = time.perf_counter()
        status, headers, body = self._post(payload)
        dt = time.perf_counter() - t0
        if status != 200:
            raise RuntimeError(f"initialize -> HTTP {status}: {body[:200]!r}")
        if headers.get("mcp-session-id"):
            self.session_id = headers["mcp-session-id"]
        msg = self._extract_json(body, headers.get("content-type", ""), request_id)
        if not msg or "result" not in msg:
            raise RuntimeError(f"initialize produced no result: {body[:300]!r}")
        return dt, msg["result"]

    def notify_initialized(self) -> tuple[float, int]:
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        t0 = time.perf_counter()
        status, _headers, body = self._post(payload)
        dt = time.perf_counter() - t0
        if status not in (200, 202):
            raise RuntimeError(
                f"notifications/initialized -> HTTP {status}: {body[:200]!r}"
            )
        return dt, status

    def list_tools(self, request_id: int) -> tuple[float, int]:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {},
        }
        t0 = time.perf_counter()
        status, headers, body = self._post(payload)
        dt = time.perf_counter() - t0
        msg = self._extract_json(body, headers.get("content-type", ""), request_id)
        n_tools = None
        if msg and "result" in msg:
            n_tools = len(msg["result"].get("tools", []))
        if status != 200 or n_tools is None:
            raise RuntimeError(f"tools/list failed -> HTTP {status}: {body[:200]!r}")
        return dt, n_tools

    def call_tool(self, request_id: int, name: str, arguments: dict) -> tuple[float, bool]:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        t0 = time.perf_counter()
        status, headers, body = self._post(payload)
        dt = time.perf_counter() - t0
        msg = self._extract_json(body, headers.get("content-type", ""), request_id)
        if status != 200 or not msg or "result" not in msg:
            raise RuntimeError(
                f"tools/call {name} failed -> HTTP {status}: {body[:300]!r}"
            )
        return dt, bool(msg["result"].get("isError", False))

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def reopen(self):
        """Drop any existing connection (models a fresh per-run client)."""
        self.close()
        self.session_id = None


# --------------------------------------------------------------------------
# One "open" = the full handshake sequence, each phase timed
# --------------------------------------------------------------------------


def one_open(client: Http1Client, call_tool_spec, request_id_base: int) -> dict:
    """Fresh connection + initialize + initialized + tools/list (+ warm call)."""
    client.reopen()
    rid = request_id_base
    timings = client.connect()
    init_s, result = client.initialize(rid)
    rid += 1
    initd_s, initd_status = client.notify_initialized()
    tools_s, n_tools = client.list_tools(rid)
    rid += 1
    total_open = timings.tcp + timings.tls + init_s + initd_s + tools_s
    out = {
        "tcp_s": timings.tcp,
        "tls_s": timings.tls,
        "initialize_s": init_s,
        "initialized_s": initd_s,
        "tools_list_s": tools_s,
        "total_open_s": total_open,
        "n_tools": n_tools,
        "session_id_issued": client.session_id is not None,
        "initialized_status": initd_status,
        "call_s": None,
        "call_is_error": None,
    }
    if call_tool_spec:
        name, args = call_tool_spec
        call_s, is_err = client.call_tool(rid, name, args)
        out["call_s"] = call_s
        out["call_is_error"] = is_err
        rid += 1
    # a repeated tools/list on the warm connection is served from an in-process
    # tool registry on every server tested, so its round-trip approximates the
    # pure transport RTT (1x TCP+TLS reuse, 0 server-side work)
    rtt_s, _n = client.list_tools(rid)
    out["warm_rtt_s"] = rtt_s
    return out


def percentile(values, p: float) -> float:
    """Nearest-rank percentile on sorted values (p in [0, 1])."""
    if not values:
        return float("nan")
    s = sorted(values)
    idx = max(0, min(len(s) - 1, math.ceil(p * len(s)) - 1))
    return s[idx]


def fmt(ms: float) -> str:
    if math.isnan(ms):
        return "-"
    return f"{ms:8.1f}"


def bench_one(label: str, url: str, runs: int, timeout: float, call_spec, sleep_s: float):
    print(f"\n=== {label} — {url} (n={runs}, timeout={timeout}s) ===")
    client = Http1Client(url, timeout=timeout)
    client.resolve()
    samples = {k: [] for k in ("tcp_s", "tls_s", "initialize_s", "initialized_s", "tools_list_s", "total_open_s", "call_s", "warm_rtt_s")}
    reconns = 0
    n_tools = None
    session_issued = None
    failures = 0
    tools_listed = 0
    # warm-up (dns, server cold start); not counted
    try:
        one_open(client, None, 9000)
    except Exception as e:  # noqa: BLE001
        print(f"  warm-up failed: {e}")
    for i in range(runs):
        try:
            s = one_open(client, call_spec, 10_000 + i)
            for k in samples:
                if s[k] is not None:
                    samples[k].append(s[k])
            reconns += client.reconnects
            client.reconnects = 0
            n_tools = s["n_tools"]
            session_issued = s["session_id_issued"]
            tools_listed += 1
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  run {i + 1} failed: {type(e).__name__}: {e}")
            client.reopen()
        if sleep_s:
            time.sleep(sleep_s)
    client.close()

    if not samples["total_open_s"]:
        print("  ALL RUNS FAILED")
        return None, url
    print(f"  sessions opened successfully: {tools_listed}/{runs}  "
          f"(failures: {failures}, mid-handshake reconnects: {reconns})")
    if n_tools is not None:
        print(f"  tools/list returned {n_tools} tools; "
              f"session id issued: {session_issued}")
    headers = ["metric", "p50 (ms)", "p95 (ms)", "min (ms)", "max (ms)"]
    rows = []
    for name in ("tcp", "tls", "initialize", "initialized", "tools_list", "total_open"):
        key = name + "_s"
        if not samples[key]:
            continue
        vals = [v * 1000 for v in samples[key]]
        rows.append([name, percentile(vals, 0.5), percentile(vals, 0.95), min(vals), max(vals)])
    colw = max(max(len(h) for h in headers), max(len(r[0]) for r in rows)) + 2
    print("  " + "".join(f"{h:<{colw}}" for h in headers))
    for r in rows:
        cells = f"{r[0]:<{colw}}" + "".join(f"{fmt(v):>10s}" for v in r[1:]) + "   "
        print("  " + cells)
    if samples["call_s"]:
        vals = [v * 1000 for v in samples["call_s"]]
        print(f"\n  warm tools/call (same connection, after handshake): "
              f"p50={percentile(vals, 0.5):.1f} ms  p95={percentile(vals, 0.95):.1f} ms  "
              f"min={min(vals):.1f}  max={max(vals):.1f}")
        h = percentile([v * 1000 for v in samples["total_open_s"]], 0.5)
        c = percentile(vals, 0.5)
        print(f"  handshake/warm-call ratio (p50): {h:.1f} / {c:.1f} = {h / c:.2f}x")
    if samples["warm_rtt_s"]:
        vals = [v * 1000 for v in samples["warm_rtt_s"]]
        print(f"  warm transport RTT (repeat tools/list, trivial server work): "
              f"p50={percentile(vals, 0.5):.1f} ms  p95={percentile(vals, 0.95):.1f} ms  "
              f"min={min(vals):.1f}  max={max(vals):.1f}")
    return samples, url


def print_derived(samples: dict, label: str, ks=(1, 3, 10)):
    """Per-run (1 handshake + k warm calls) vs per-tool-call (k handshakes), p50."""
    if not samples or not samples["total_open_s"]:
        return
    hs = percentile([v * 1000 for v in samples["total_open_s"]], 0.5)
    calls = samples["call_s"]
    per_call_p50 = percentile([v * 1000 for v in calls], 0.5) if calls else None
    basis = "warm tools/call p50"
    if per_call_p50 is None:
        # fall back to the transport-RTT floor so the derivation stays comparable
        per_call_p50 = percentile([v * 1000 for v in samples["warm_rtt_s"]], 0.5)
        basis = "warm RTT floor (no tools/call measured)"
    print(f"\n  derived comparison ({label}, p50, per a run made of N tool calls; "
          f"per-call basis: {basis} = {per_call_p50:.1f} ms):")
    print(f"    {'tool calls':>10} | {'per-run (1 open + N calls)':>28} | "
          f"{'per-tool-call (N opens + N calls)':>34} | {'overhead':>9}")
    for k in ks:
        per_run = hs + k * per_call_p50
        per_call = k * (hs + per_call_p50)
        overhead = per_call - per_run
        print(f"    {k:>10} | {per_run:>25.1f} ms | {per_call:>31.1f} ms | "
              f"{overhead:>8.1f} ms")


# --------------------------------------------------------------------------
# Local reference server (optional, needs fastmcp)
# --------------------------------------------------------------------------


def serve_local(host: str, port: int):
    """Tiny Streamable HTTP reference server: one trivial `add` tool."""
    try:
        from fastmcp import FastMCP
    except ImportError:
        sys.exit("serve-local needs fastmcp: create a venv and `uv pip install fastmcp`")
    mcp = FastMCP("ags-handshake-bench-ref")

    @mcp.tool
    def add(a: int, b: int) -> int:
        """Add two integers (trivial reference tool for warm-call timing)."""
        return a + b

    mcp.run(transport="http", host=host, port=port)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_kv(items, what):
    out = {}
    for item in items or []:
        if "=" not in item:
            sys.exit(f"--{what} must be LABEL=VALUE, got {item!r}")
        k, _, v = item.partition("=")
        out[k] = v
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "serve-local":
        sub = argparse.ArgumentParser(description="run the local reference MCP server (fastmcp)")
        sub.add_argument("--host", default="127.0.0.1")
        sub.add_argument("--port", type=int, default=8123)
        sargs = sub.parse_args(argv[1:])
        serve_local(sargs.host, sargs.port)
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", default=[], metavar="LABEL=URL",
                    help="server to benchmark (repeatable)")
    ap.add_argument("--call-tool", action="append", default=[], metavar="LABEL=TOOL",
                    help="tool to call once per open on the warm connection (per LABEL)")
    ap.add_argument("--call-args", action="append", default=[], metavar="LABEL=JSON",
                    help="arguments for --call-tool (per LABEL, default {})")
    ap.add_argument("--runs", type=int, default=20, help="handshakes to time per server (>= 20)")
    ap.add_argument("--timeout", type=float, default=15.0, help="per-request socket timeout (s)")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between handshakes")
    ap.add_argument("--derive-k", type=int, nargs="+", default=[1, 3, 10],
                    help="k values for the per-run vs per-tool-call derivation")
    args = ap.parse_args(argv)

    if not args.url:
        sys.exit("no --url given")
    if args.runs < 1:
        sys.exit("--runs must be >= 1")

    tools = parse_kv(args.call_tool, "call-tool")
    cargs = parse_kv(args.call_args, "call-args")

    all_samples = {}
    for spec in args.url:
        label, _, url = spec.partition("=")
        if not url:
            label, url = f"s{len(all_samples) + 1}", spec
        call_spec = None
        tool_name = tools.get(label)
        if tool_name:
            call_spec = (tool_name, json.loads(cargs.get(label, "{}")))
        samples, url = bench_one(label, url, args.runs, args.timeout, call_spec, args.sleep)
        all_samples[label] = samples
        print_derived(samples, label, tuple(args.derive_k))
    print("\ndone.")


if __name__ == "__main__":
    main()