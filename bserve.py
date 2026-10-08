#!/usr/bin/env python3
"""
bserve — BHTP File Server (Track 1)
====================================

Usage:  python bserve.py <webroot> <port>

Serves files from <webroot> over the BHTP binary protocol.
Keeps TCP connections open for multiple sequential requests.
Returns 404 if a file is not found, 400 if a frame is malformed.
"""

import sys
import os
import socket
import threading
import mimetypes
import datetime

from bhtp import (
    Frame,
    TYPE_REQUEST,
    TYPE_RESPONSE,
    FLAG_END_STREAM,
    STATUS_OK,
    STATUS_BAD_REQ,
    STATUS_NOT_FOUND,
    STATUS_INTERNAL,
    encode_frame,
    decode_frame,
    MalformedFrameError,
)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def send_response(conn, status, headers, body=b""):
    """Build and send a single BHTP response frame."""
    frame = Frame(
        frame_type=TYPE_RESPONSE,
        flags=0,
        status=status,
        headers=headers,
        body=body,
    )
    conn.sendall(encode_frame(frame))


def send_error(conn, status, message):
    """Send a plain-text error response."""
    body = message.encode("utf-8")
    send_response(conn, status, [
        ("content-type", "text/plain"),
        ("content-length", str(len(body))),
        ("server", "bserve/1.0"),
    ], body)


# ---------------------------------------------------------------------------
# Connection handler (runs in its own thread)
# ---------------------------------------------------------------------------

def handle_connection(conn, addr, webroot):
    """Handle one persistent TCP connection.

    Reads request frames in a loop until the client disconnects or
    signals END_STREAM.
    """
    peer = f"{addr[0]}:{addr[1]}"
    print(f"[+] Connection from {peer}")

    try:
        while True:
            # ---- Read one request frame ----
            try:
                frame, _raw = decode_frame(conn)
            except MalformedFrameError as exc:
                print(f"[!] Malformed frame from {peer}: {exc}")
                try:
                    send_error(conn, STATUS_BAD_REQ, f"Bad Request: {exc}")
                except OSError:
                    pass
                break   # cannot recover framing, must close

            if frame is None:
                break   # client closed the connection cleanly

            # decode_frame already skips unknown types, so if we get
            # here the type is guaranteed to be REQUEST or RESPONSE.
            if frame.frame_type != TYPE_REQUEST:
                # A response from the client is nonsensical — ignore.
                continue

            # ---- Extract pseudo-headers ----
            method = frame.get_header(":method")
            path   = frame.get_header(":path")

            if method is None or path is None:
                send_error(
                    conn, STATUS_BAD_REQ,
                    "Missing required pseudo-header: :method or :path",
                )
                if frame.flags & FLAG_END_STREAM:
                    break
                continue

            print(f"    {method} {path} from {peer}")

            # ---- Resolve filesystem path ----
            clean_path = path.split("?")[0].split("#")[0]   # strip query / fragment
            rel = clean_path.lstrip("/")
            if not rel:
                rel = "index.html"    # default document

            filepath = os.path.normpath(os.path.join(webroot, rel))
            abs_root = os.path.normpath(os.path.abspath(webroot))

            # Path-traversal protection
            if not filepath.startswith(abs_root + os.sep) and filepath != abs_root:
                print(f"    -> 404 (path traversal blocked)")
                send_error(conn, STATUS_NOT_FOUND, "Not Found")
                if frame.flags & FLAG_END_STREAM:
                    break
                continue

            if not os.path.isfile(filepath):
                print(f"    -> 404")
                send_error(conn, STATUS_NOT_FOUND, f"Not Found: {path}")
                if frame.flags & FLAG_END_STREAM:
                    break
                continue

            # ---- Read file ----
            try:
                with open(filepath, "rb") as fh:
                    body = fh.read()
            except OSError as exc:
                print(f"    -> 500 ({exc})")
                send_error(conn, STATUS_INTERNAL, f"Internal Server Error")
                if frame.flags & FLAG_END_STREAM:
                    break
                continue

            # ---- Determine MIME type ----
            content_type, _ = mimetypes.guess_type(filepath)
            if content_type is None:
                content_type = "application/octet-stream"

            # ---- Build & send response ----
            now = datetime.datetime.now(datetime.UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
            resp_headers = [
                ("content-type",   content_type),
                ("content-length", str(len(body))),
                ("server",         "bserve/1.0"),
                ("date",           now),
            ]

            send_response(conn, STATUS_OK, resp_headers, body)
            print(f"    -> 200 ({len(body)} bytes, {content_type})")

            # If the client signalled END_STREAM, stop reading.
            if frame.flags & FLAG_END_STREAM:
                break

    except ConnectionResetError:
        print(f"[!] Connection reset by {peer}")
    except BrokenPipeError:
        print(f"[!] Broken pipe to {peer}")
    except Exception as exc:
        print(f"[!] Unexpected error with {peer}: {exc}")
    finally:
        conn.close()
        print(f"[-] Disconnected {peer}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <webroot> <port>", file=sys.stderr)
        sys.exit(1)

    webroot = sys.argv[1]

    try:
        port = int(sys.argv[2])
    except ValueError:
        print(f"Error: Invalid port number: {sys.argv[2]}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(webroot):
        print(f"Error: Web root '{webroot}' is not a directory", file=sys.stderr)
        sys.exit(1)

    webroot = os.path.abspath(webroot)

    # ---- Set up the listening socket ----
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)

    print(f"bserve listening on :{port}  root={webroot}")
    print(f"Press Ctrl+C to stop.\n")

    try:
        while True:
            conn, addr = srv.accept()
            thread = threading.Thread(
                target=handle_connection,
                args=(conn, addr, webroot),
                daemon=True,
            )
            thread.start()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
