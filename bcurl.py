#!/usr/bin/env python3
"""
bcurl — BHTP Client (Track 2)
===============================

Usage:  python bcurl.py [-v] <host>:<port>/<path>

Builds a BHTP binary request frame, sends it over a single TCP
connection, reads the response, and writes the body to stdout.

Options:
    -v    Verbose mode — hexdumps every frame to stderr.

Exit codes:
    0     Success (status < 400).
    1     Server returned 4xx or 5xx.
"""

import sys
import socket

from bhtp import (
    Frame,
    TYPE_REQUEST,
    FLAG_END_STREAM,
    encode_frame,
    decode_frame,
    hexdump,
    MalformedFrameError,
)


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def parse_target(target):
    """Parse ``host:port/path`` into (host, port, path).

    Examples
    --------
    >>> parse_target("localhost:9000/index.html")
    ('localhost', 9000, '/index.html')
    >>> parse_target("127.0.0.1:8080/")
    ('127.0.0.1', 8080, '/')
    """
    slash_idx = target.find("/")
    if slash_idx == -1:
        host_port = target
        path = "/"
    else:
        host_port = target[:slash_idx]
        path = target[slash_idx:]      # includes the leading /

    if ":" not in host_port:
        raise ValueError(f"Missing port in target: {target!r}")

    host, port_str = host_port.rsplit(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        raise ValueError(f"Invalid port: {port_str!r}")

    if not path:
        path = "/"

    return host, port, path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args or args == ["-v"]:
        print(f"Usage: python {sys.argv[0]} [-v] <host>:<port>/<path>",
              file=sys.stderr)
        sys.exit(1)

    # ---- Parse flags ----
    verbose = False
    if "-v" in args:
        verbose = True
        args.remove("-v")

    target = args[0]

    try:
        host, port, path = parse_target(target)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # ---- Build the request frame ----
    req = Frame(
        frame_type=TYPE_REQUEST,
        flags=FLAG_END_STREAM,      # single request, then done
        status=0,                   # not used in requests
        headers=[
            (":method",    "GET"),
            (":path",      path),
            (":host",      f"{host}:{port}"),
            ("accept",     "*/*"),
            ("user-agent", "bcurl/1.0"),
        ],
        body=b"",
    )

    raw_req = encode_frame(req)

    # ---- Connect (one socket — never a second) ----
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except ConnectionRefusedError:
        print(f"Error: Connection refused — {host}:{port}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # ---- Verbose: show request ----
    if verbose:
        print(f"* Connected to {host}:{port}", file=sys.stderr)
        print(f"* Sending REQUEST frame ({len(raw_req)} bytes)", file=sys.stderr)
        print(file=sys.stderr)
        print(f">> REQUEST FRAME ({len(raw_req)} bytes)", file=sys.stderr)
        print(hexdump(raw_req, ">> "), file=sys.stderr)
        print(file=sys.stderr)

    # ---- Send ----
    sock.sendall(raw_req)

    # ---- Receive response ----
    try:
        resp, raw_resp = decode_frame(sock)
    except MalformedFrameError as exc:
        print(f"Error: Malformed response from server: {exc}", file=sys.stderr)
        sock.close()
        sys.exit(1)

    if resp is None:
        print("Error: Server closed connection without sending a response",
              file=sys.stderr)
        sock.close()
        sys.exit(1)

    # ---- Verbose: show response ----
    if verbose:
        print(f"<< RESPONSE FRAME ({len(raw_resp)} bytes)", file=sys.stderr)
        print(hexdump(raw_resp, "<< "), file=sys.stderr)
        print(file=sys.stderr)

        # Decoded summary
        print(f"<< Status: {resp.status}", file=sys.stderr)
        for name, value in resp.headers:
            print(f"<< {name}: {value}", file=sys.stderr)
        print(f"<< Body: {len(resp.body)} bytes", file=sys.stderr)
        print(file=sys.stderr)

    # ---- Write body to stdout ----
    sys.stdout.buffer.write(resp.body)
    sys.stdout.buffer.flush()

    # ---- Clean up ----
    sock.close()

    # ---- Exit non-zero on 4xx / 5xx ----
    if resp.status >= 400:
        sys.exit(1)


if __name__ == "__main__":
    main()
