# BHTP — Binary HTTP Transfer Protocol Specification

**Version 1.0** • October 2026

---

## 1. Overview

BHTP is a binary application-layer protocol for transferring hypertext resources
over a single, persistent TCP connection. It is inspired by HTTP/2's binary
framing layer but removes multiplexing, providing a simpler request–response
model suitable for file serving.

All multi-byte integers in BHTP are **big-endian** (network byte order).

---

## 2. Frame Format

Every BHTP message (request or response) is carried in exactly **one frame**.
A frame consists of a fixed 9-byte header followed by a variable-length payload.

### 2.1 Frame Header (9 bytes)

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

| Offset | Field            | Width    | Description                                             |
|--------|------------------|----------|---------------------------------------------------------|
| 0–2    | Payload Length    | 24 bits  | Number of bytes in the payload (max 16,777,215).        |
| 3      | Frame Type       | 8 bits   | `0x01` = REQUEST, `0x02` = RESPONSE.                    |
| 4      | Flags            | 8 bits   | Bit 0 (`0x01`): END_STREAM — no more frames will follow.|
| 5–6    | Status Code      | 16 bits  | `0` for requests. HTTP status code for responses (e.g., 200, 404). |
| 7      | Header Count     | 8 bits   | Number of header entries in the payload.                 |
| 8      | Reserved         | 8 bits   | Must be `0x00` on send; ignored on receive.             |

**Design rationale (cf. HTTP/2's 24/8/8/31):**  
HTTP/2 uses a 31-bit stream identifier because it multiplexes many streams over
one connection. BHTP uses a single request–response sequence at a time, so the
stream ID is replaced by a status code (useful in the header for fast dispatch)
and a header count (eliminates the need for a separate headers-length field).

### 2.2 Payload

```
+---------------------------+-------------------------------+
|   Header Block (variable) |        Body (variable)        |
+---------------------------+-------------------------------+
```

The payload begins with exactly **Header Count** encoded header entries
(see §3), followed by the remaining bytes which constitute the **body**.

---

## 3. Header Encoding (HPACK-lite)

Headers are encoded using two mechanisms inspired by HPACK (RFC 7541):

### 3.1 Static Table (Indexed Names)

The following 10 header names are assigned fixed indices and need only a single
byte on the wire:

| Index | Header Name      | Index | Header Name      |
|-------|------------------|-------|------------------|
| `0x00`| `:method`        | `0x05`| `server`         |
| `0x01`| `:path`          | `0x06`| `date`            |
| `0x02`| `:host`          | `0x07`| `connection`     |
| `0x03`| `content-type`   | `0x08`| `accept`         |
| `0x04`| `content-length` | `0x09`| `user-agent`     |

### 3.2 Header Entry Wire Format

**Indexed name** (name exists in the static table):
```
+------------+-------------------+---------------------+
| Index (1B) | Value Length (2B) |   Value (N bytes)   |
+------------+-------------------+---------------------+
```

**Literal name** (name is not in the static table):
```
+--------+------------------+----------------+-------------------+---------------------+
| 0xFF   | Name Length (2B)  | Name (M bytes) | Value Length (2B) |   Value (N bytes)   |
+--------+------------------+----------------+-------------------+---------------------+
```

- The **marker byte** `0xFF` distinguishes literal names from indexed names
  (valid indices are `0x00`–`0x09`).
- **Name Length** and **Value Length** are 16-bit unsigned big-endian integers.
- Name and value data are UTF-8 encoded.

---

## 4. Frame Types

| Code   | Name       | Direction       | Description                                  |
|--------|------------|-----------------|----------------------------------------------|
| `0x01` | REQUEST    | Client → Server | Carries method, path, headers, and optional body. Status field must be 0. |
| `0x02` | RESPONSE   | Server → Client | Carries status code, headers, and body.       |

All other type codes (`0x00`, `0x03`–`0xFF`) are reserved for future versions.

### 4.1 Forward Compatibility (Mandatory Rule)

> **A receiver encountering a frame type it does not recognise MUST read and
> discard exactly Payload Length bytes, then continue processing subsequent
> frames.** An implementation MUST NOT close the connection or return an error
> when it encounters an unknown frame type.

This rule ensures that a v1 implementation can interoperate with a v2 peer that
sends new frame types.

---

## 5. Connection Semantics

1. The client opens **one** TCP connection to the server.
2. The client sends a REQUEST frame; the server replies with a RESPONSE frame.
3. The connection remains open for further request–response pairs.
4. Setting `END_STREAM` (flag bit 0) on a frame signals that the sender will
   not send any more frames. The receiver should finish processing and close.
5. Either side may close the TCP connection at any time; the peer detects this
   as a clean close if it occurs at a frame boundary.

---

## 6. Status Codes

BHTP reuses standard HTTP status codes in the 16-bit status field:

| Code | Meaning             | When Used                                    |
|------|---------------------|----------------------------------------------|
| 200  | OK                  | File found and served successfully.           |
| 400  | Bad Request         | Frame is malformed or missing required headers.|
| 404  | Not Found           | Requested path does not map to a file.        |
| 500  | Internal Server Error | Server encountered an unexpected condition.  |

A client MUST treat any status ≥ 400 as an error.

---

## 7. Required Pseudo-Headers

A REQUEST frame **must** include at least these headers:

| Header    | Example Value | Purpose             |
|-----------|---------------|---------------------|
| `:method` | `GET`         | The request method.  |
| `:path`   | `/index.html` | The resource path.   |

A RESPONSE frame **should** include:

| Header           | Example Value                        |
|------------------|--------------------------------------|
| `content-type`   | `text/html`                          |
| `content-length` | `312`                                |
| `server`         | `bserve/1.0`                         |
| `date`           | `Sun, 04 Oct 2026 16:54:00 GMT`      |

---

## 8. Error Handling

- **Malformed frame**: If the server cannot parse a frame (truncated header,
  invalid header index, etc.), it sends a `400 Bad Request` response and closes
  the connection (framing sync is lost).
- **File not found**: The server sends a `404 Not Found` response and keeps the
  connection open for further requests.
- **Path traversal**: Any path that resolves outside the web root is treated as
  `404 Not Found`.
