#!/usr/bin/env python3
"""
test_bhtp.py — End-to-end tests for the BHTP protocol
======================================================

Tests:
  1. Unit tests for bhtp.py (encode/decode roundtrip, unknown frame skip)
  2. Integration tests: start bserve, hit it with bcurl
"""

import sys
import os
import socket
import time
import struct
import subprocess
import threading

# Ensure we can import from the project directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bhtp import (
    Frame, encode_frame, decode_frame, encode_headers, decode_headers,
    hexdump, MalformedFrameError,
    TYPE_REQUEST, TYPE_RESPONSE, FLAG_END_STREAM,
    STATUS_OK, STATUS_BAD_REQ, STATUS_NOT_FOUND,
    FRAME_HEADER_SIZE, STATIC_TABLE, LITERAL_NAME_MARKER,
)

PASSED = 0
FAILED = 0


def test(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        print(f"  [PASS] {name}")
        PASSED += 1
    else:
        print(f"  [FAIL] {name}  {detail}")
        FAILED += 1


# ==========================================================================
# Unit Tests
# ==========================================================================

def test_header_roundtrip():
    """Encode headers, decode them, verify they match."""
    print("\n--- Header Encoding Roundtrip ---")

    headers = [
        (":method", "GET"),
        (":path", "/index.html"),
        ("content-type", "text/html"),
        ("x-custom-header", "custom-value"),   # literal name
    ]

    encoded = encode_headers(headers)
    decoded, consumed = decode_headers(encoded, len(headers))

    test("header count matches", len(decoded) == len(headers),
         f"expected {len(headers)}, got {len(decoded)}")

    for i, ((en, ev), (dn, dv)) in enumerate(zip(headers, decoded)):
        test(f"header[{i}] name", en == dn, f"{en!r} != {dn!r}")
        test(f"header[{i}] value", ev == dv, f"{ev!r} != {dv!r}")

    test("all bytes consumed", consumed == len(encoded),
         f"consumed {consumed}/{len(encoded)}")


def test_frame_roundtrip():
    """Encode a frame, feed it to decode_frame via a socket pair, verify."""
    print("\n--- Frame Encode/Decode Roundtrip ---")

    original = Frame(
        frame_type=TYPE_REQUEST,
        flags=FLAG_END_STREAM,
        status=0,
        headers=[
            (":method", "GET"),
            (":path", "/hello.txt"),
            (":host", "localhost:9000"),
            ("accept", "*/*"),
            ("user-agent", "test/1.0"),
        ],
        body=b"",
    )

    raw = encode_frame(original)
    test("encoded length > 9", len(raw) > FRAME_HEADER_SIZE)

    # Verify header fields in the raw bytes
    payload_len = (raw[0] << 16) | (raw[1] << 8) | raw[2]
    test("payload length correct", payload_len == len(raw) - FRAME_HEADER_SIZE,
         f"header says {payload_len}, actual {len(raw) - FRAME_HEADER_SIZE}")
    test("frame type", raw[3] == TYPE_REQUEST)
    test("flags", raw[4] == FLAG_END_STREAM)
    test("status high byte", raw[5] == 0)
    test("status low byte", raw[6] == 0)
    test("header count", raw[7] == len(original.headers))
    test("reserved", raw[8] == 0x00)

    # Decode via socket pair
    s1, s2 = socket.socketpair()
    s1.sendall(raw)
    s1.close()

    decoded, raw_recv = decode_frame(s2)
    s2.close()

    test("decoded is not None", decoded is not None)
    test("type matches", decoded.frame_type == original.frame_type)
    test("flags match", decoded.flags == original.flags)
    test("status matches", decoded.status == original.status)
    test("header count matches", len(decoded.headers) == len(original.headers))
    test("body matches", decoded.body == original.body)
    test("raw bytes match", raw_recv == raw)


def test_response_frame():
    """Test encoding/decoding a response frame with a body."""
    print("\n--- Response Frame ---")

    body = b"Hello, BHTP!\n"
    original = Frame(
        frame_type=TYPE_RESPONSE,
        flags=0,
        status=STATUS_OK,
        headers=[
            ("content-type", "text/plain"),
            ("content-length", str(len(body))),
            ("server", "test/1.0"),
        ],
        body=body,
    )

    raw = encode_frame(original)

    s1, s2 = socket.socketpair()
    s1.sendall(raw)
    s1.close()

    decoded, _ = decode_frame(s2)
    s2.close()

    test("type is RESPONSE", decoded.frame_type == TYPE_RESPONSE)
    test("status is 200", decoded.status == 200)
    test("body matches", decoded.body == body)
    test("content-type header", decoded.get_header("content-type") == "text/plain")
    test("content-length header", decoded.get_header("content-length") == str(len(body)))


def test_unknown_frame_skip():
    """Send an unknown frame type followed by a known one — verify skip."""
    print("\n--- Unknown Frame Type Skipping ---")

    # Build an unknown frame (type 0xAA) manually
    unknown_payload = b"this is unknown data that should be skipped"
    unknown_len = len(unknown_payload)
    unknown_hdr = bytearray(FRAME_HEADER_SIZE)
    unknown_hdr[0] = (unknown_len >> 16) & 0xFF
    unknown_hdr[1] = (unknown_len >>  8) & 0xFF
    unknown_hdr[2] =  unknown_len        & 0xFF
    unknown_hdr[3] = 0xAA  # unknown type!
    unknown_hdr[4] = 0x00
    unknown_hdr[5] = 0x00
    unknown_hdr[6] = 0x00
    unknown_hdr[7] = 0x00  # 0 headers
    unknown_hdr[8] = 0x00

    unknown_frame_bytes = bytes(unknown_hdr) + unknown_payload

    # Build a known REQUEST frame
    known = Frame(
        frame_type=TYPE_REQUEST,
        flags=0,
        status=0,
        headers=[(":method", "GET"), (":path", "/")],
        body=b"",
    )
    known_bytes = encode_frame(known)

    # Send unknown + known
    s1, s2 = socket.socketpair()
    s1.sendall(unknown_frame_bytes + known_bytes)
    s1.close()

    decoded, _ = decode_frame(s2)
    s2.close()

    test("unknown frame was skipped", decoded is not None)
    test("decoded frame is the known one", decoded.frame_type == TYPE_REQUEST)
    test("path header correct", decoded.get_header(":path") == "/")


def test_hexdump_output():
    """Verify hexdump produces readable output."""
    print("\n--- Hexdump Utility ---")

    data = bytes(range(32))
    output = hexdump(data, "  ")

    test("hexdump has lines", len(output.strip().split("\n")) == 2)
    test("hexdump contains hex", "00 01 02" in output)
    test("hexdump has ASCII column", "|" in output)


def test_literal_header():
    """Test encoding a header with a non-indexed name."""
    print("\n--- Literal Header Name ---")

    headers = [("x-request-id", "abc-123")]
    encoded = encode_headers(headers)

    # First byte should be LITERAL_NAME_MARKER
    test("literal marker", encoded[0] == LITERAL_NAME_MARKER)

    decoded, consumed = decode_headers(encoded, 1)
    test("name decoded", decoded[0][0] == "x-request-id")
    test("value decoded", decoded[0][1] == "abc-123")


def test_status_404():
    """Test that status code 404 survives roundtrip (16-bit field)."""
    print("\n--- Status Code 404 Roundtrip ---")

    frame = Frame(
        frame_type=TYPE_RESPONSE,
        flags=0,
        status=STATUS_NOT_FOUND,
        headers=[("content-type", "text/plain")],
        body=b"Not Found",
    )

    raw = encode_frame(frame)

    s1, s2 = socket.socketpair()
    s1.sendall(raw)
    s1.close()

    decoded, _ = decode_frame(s2)
    s2.close()

    test("status is 404", decoded.status == 404)
    test("body is 'Not Found'", decoded.body == b"Not Found")


# ==========================================================================
# Integration Tests (server + client)
# ==========================================================================

def test_integration():
    """Start bserve, use bcurl to fetch files, verify results."""
    print("\n--- Integration Tests ---")

    project_dir = os.path.dirname(os.path.abspath(__file__))
    www_dir = os.path.join(project_dir, "www")
    port = 19876   # use a high port to avoid conflicts

    # Start the server
    server_proc = subprocess.Popen(
        [sys.executable, os.path.join(project_dir, "bserve.py"), www_dir, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=project_dir,
    )

    time.sleep(1)  # give the server time to bind

    try:
        # -- Test 1: Fetch hello.txt --
        print("  [....] Fetching /hello.txt ...")
        result = subprocess.run(
            [sys.executable, os.path.join(project_dir, "bcurl.py"),
             f"localhost:{port}/hello.txt"],
            capture_output=True, timeout=5, cwd=project_dir,
        )
        test("hello.txt exit code 0", result.returncode == 0,
             f"got {result.returncode}")
        test("hello.txt body correct",
             result.stdout.strip() == b"Hello, BHTP!",
             f"got {result.stdout!r}")

        # -- Test 2: Fetch index.html --
        print("  [....] Fetching /index.html ...")
        result = subprocess.run(
            [sys.executable, os.path.join(project_dir, "bcurl.py"),
             f"localhost:{port}/index.html"],
            capture_output=True, timeout=5, cwd=project_dir,
        )
        test("index.html exit code 0", result.returncode == 0)
        test("index.html contains <h1>", b"<h1>" in result.stdout)

        # -- Test 3: 404 for missing file --
        print("  [....] Fetching /nonexistent.txt (expect 404) ...")
        result = subprocess.run(
            [sys.executable, os.path.join(project_dir, "bcurl.py"),
             f"localhost:{port}/nonexistent.txt"],
            capture_output=True, timeout=5, cwd=project_dir,
        )
        test("404 exit code non-zero", result.returncode != 0,
             f"got {result.returncode}")

        # -- Test 4: Verbose mode --
        print("  [....] Verbose fetch /hello.txt ...")
        result = subprocess.run(
            [sys.executable, os.path.join(project_dir, "bcurl.py"),
             "-v", f"localhost:{port}/hello.txt"],
            capture_output=True, timeout=5, cwd=project_dir,
        )
        test("verbose exit code 0", result.returncode == 0)
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        test("verbose shows REQUEST FRAME", "REQUEST FRAME" in stderr_text,
             f"stderr: {stderr_text[:200]}")
        test("verbose shows RESPONSE FRAME", "RESPONSE FRAME" in stderr_text)
        test("verbose shows hex bytes", "00000000" in stderr_text)

        # -- Test 5: Path traversal blocked --
        print("  [....] Path traversal attempt ...")
        result = subprocess.run(
            [sys.executable, os.path.join(project_dir, "bcurl.py"),
             f"localhost:{port}/../../../etc/passwd"],
            capture_output=True, timeout=5, cwd=project_dir,
        )
        test("path traversal blocked (non-zero exit)", result.returncode != 0)

        # -- Test 6: Fetch style.css (different MIME type) --
        print("  [....] Fetching /style.css ...")
        result = subprocess.run(
            [sys.executable, os.path.join(project_dir, "bcurl.py"),
             "-v", f"localhost:{port}/style.css"],
            capture_output=True, timeout=5, cwd=project_dir,
        )
        test("style.css exit code 0", result.returncode == 0)
        test("style.css body has CSS", b"font-family" in result.stdout)
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        test("style.css content-type is text/css", "text/css" in stderr_text,
             f"stderr: {stderr_text[:300]}")

    finally:
        server_proc.terminate()
        server_proc.wait(timeout=5)


# ==========================================================================
# Main
# ==========================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("BHTP Test Suite")
    print("=" * 60)

    test_header_roundtrip()
    test_frame_roundtrip()
    test_response_frame()
    test_unknown_frame_skip()
    test_hexdump_output()
    test_literal_header()
    test_status_404()
    test_integration()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed")
    print("=" * 60)

    sys.exit(1 if FAILED > 0 else 0)
