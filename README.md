# BHTP — Binary HTTP Transfer Protocol

A binary application-layer protocol for transferring files over TCP, inspired by HTTP/2's binary framing layer. Built as a course project exploring protocol design, binary encoding, and header compression.

## Overview

BHTP replaces HTTP/1.1's text-based request format with a compact binary frame structure. Every message — request or response — is a single frame with a **9-byte fixed header** followed by compressed headers and a body.

The project implements:
- **`bserve`** — a file-serving TCP server (Track 1)
- **`bcurl`** — a command-line binary client (Track 2)
- **`bhtp`** — shared protocol library for frame encoding/decoding

## Protocol Design

### Frame Header (9 bytes)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  Payload Length (24)          |    Type (8)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Flags (8)   |         Status Code (16)      | Hdr Count (8) |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Reserved (8)  |
+-+-+-+-+-+-+-+-+
```

| Field | Width | Description |
|-------|-------|-------------|
| Payload Length | 24 bits | Bytes after the header (max 16 MB) |
| Frame Type | 8 bits | `0x01` REQUEST, `0x02` RESPONSE |
| Flags | 8 bits | Bit 0: END_STREAM |
| Status Code | 16 bits | 0 for requests; HTTP status for responses |
| Header Count | 8 bits | Number of header entries |
| Reserved | 8 bits | Must be `0x00` |

**Why these widths?** HTTP/2 uses `24/8/8/31` (the 31-bit stream ID enables multiplexing). BHTP doesn't multiplex, so we replace the stream ID with a status code and header count — fields that are actually useful in a single-stream model. The result is the same 9-byte header size.

### Header Compression (HPACK-lite)

Two mechanisms borrowed from HPACK (RFC 7541):

**1. Static Table** — The 10 most common header names are assigned 1-byte indices:

| Index | Name | Index | Name |
|-------|------|-------|------|
| `0x00` | `:method` | `0x05` | `server` |
| `0x01` | `:path` | `0x06` | `date` |
| `0x02` | `:host` | `0x07` | `connection` |
| `0x03` | `content-type` | `0x08` | `accept` |
| `0x04` | `content-length` | `0x09` | `user-agent` |

**2. Length-Prefixed Strings** — Non-indexed header names use marker `0xFF` followed by a 2-byte name length and the name bytes. Values are always 2-byte length-prefixed.

### Forward Compatibility

> **A receiver encountering a frame type it does not recognise MUST read and discard exactly Payload Length bytes, then continue.** This is how we leave room for a version 2.

## Quick Start

```bash
# Start the server
python bserve.py ./www 9000

# Fetch a file
python bcurl.py localhost:9000/hello.txt

# Fetch with hexdump (verbose mode)
python bcurl.py -v localhost:9000/index.html
```

### Verbose Output Example

```
* Connected to localhost:9000
* Sending REQUEST frame (63 bytes)

>> REQUEST FRAME (63 bytes)
>> 00000000  00 00 36 01 01 00 00 05 00 00 00 03 47 45 54 01   |..6.........GET.|
>> 00000010  00 0a 2f 68 65 6c 6c 6f 2e 74 78 74 02 00 0e 6c   |../hello.txt...l|
>> 00000020  6f 63 61 6c 68 6f 73 74 3a 39 30 30 30 08 00 03   |ocalhost:9000...|
>> 00000030  2a 2f 2a 09 00 09 62 63 75 72 6c 2f 31 2e 30      |*/*...bcurl/1.0|

<< RESPONSE FRAME (85 bytes)
<< 00000000  00 00 4c 02 00 00 c8 04 00 03 00 0a 74 65 78 74   |..L.........text|
<< 00000010  2f 70 6c 61 69 6e 04 00 02 31 33 05 00 0a 62 73   |/plain...13...bs|
...

<< Status: 200
<< content-type: text/plain
<< content-length: 13
<< Body: 13 bytes
```

## Project Structure

```
├── bhtp.py            # Shared protocol library (frame encode/decode)
├── bserve.py          # Track 1: TCP file server
├── bcurl.py           # Track 2: Binary curl client
├── test_bhtp.py       # End-to-end test suite (54 tests)
├── spec.md            # Protocol specification
├── hexdump.md         # Annotated hexdump of a complete exchange
└── www/               # Sample web root
    ├── index.html
    ├── style.css
    └── hello.txt
```

## Features

### Server (`bserve`)
- Accepts TCP connections and reads binary request frames
- Maps request paths to files under a configurable web root
- Returns `404` if a file is not found, `400` if the frame is malformed
- Path traversal protection
- **Keeps connections open** for multiple sequential requests
- Threaded for concurrent clients

### Client (`bcurl`)
- Builds binary request frames from a URL-like target
- `-v` flag hexdumps every frame to stderr
- Exits non-zero on `4xx` / `5xx` status codes
- **Never opens a second connection**

## Testing

```bash
python test_bhtp.py
```

Runs 54 tests covering:
- Header encoding roundtrips (indexed + literal names)
- Frame encode/decode roundtrips (request + response)
- Unknown frame type skipping (mandatory rule)
- Status code 404 through the 16-bit field
- Integration tests: server ↔ client for multiple files, 404s, path traversal, verbose output, and MIME type detection

## Deliverables

1. **[Protocol Specification](spec.md)** — Two-page spec, enough for a stranger to implement a compatible client or server.
2. **Programs** — `bserve.py` (server) and `bcurl.py` (client), sharing `bhtp.py`.
3. **[Annotated Hexdump](hexdump.md)** — Byte-by-byte walkthrough of one complete `GET /hello.txt` → `200 OK` exchange.

## Requirements

- Python 3.10+ (uses `match`-free code, only stdlib — no pip installs needed)
