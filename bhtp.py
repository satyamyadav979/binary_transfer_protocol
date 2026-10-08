"""
bhtp.py — Binary HTTP Transfer Protocol (BHTP) Library
=======================================================

Shared library for encoding and decoding BHTP frames, used by both
the server (bserve) and the client (bcurl).

Frame Header Layout (9 bytes, big-endian):
    Offset  Field           Width
    ------  --------------  -------
    0–2     Payload Length   24 bits   (length of everything after this header)
    3       Frame Type        8 bits   (0x01=REQUEST, 0x02=RESPONSE)
    4       Flags             8 bits   (bit 0: END_STREAM)
    5–6     Status Code      16 bits   (0 for requests; HTTP status for responses)
    7       Header Count      8 bits   (number of header entries in payload)
    8       Reserved          8 bits   (must be 0x00, ignored on read)

Header Encoding (HPACK-lite):
    Static table indices 0–9 encode the 10 most common header names
    in a single byte. All others use 0xFF followed by a length-prefixed
    literal name. Values are always length-prefixed (2-byte big-endian length).

Mandatory Rule:
    A receiver meeting a frame type it does not know MUST skip it cleanly.
    This is how we leave room for a version 2.
"""

import struct


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRAME_HEADER_SIZE = 9

# Frame types
TYPE_REQUEST  = 0x01
TYPE_RESPONSE = 0x02

# Flags (bit positions)
FLAG_END_STREAM = 0x01   # bit 0: sender will send no more frames

# Well-known HTTP status codes
STATUS_OK        = 200
STATUS_BAD_REQ   = 400
STATUS_NOT_FOUND = 404
STATUS_INTERNAL  = 500

# Static header table — indices 0 through 9
# These are the "ten names you actually send", per the assignment spec.
STATIC_TABLE = [
    ":method",         # 0x00
    ":path",           # 0x01
    ":host",           # 0x02
    "content-type",    # 0x03
    "content-length",  # 0x04
    "server",          # 0x05
    "date",            # 0x06
    "connection",      # 0x07
    "accept",          # 0x08
    "user-agent",      # 0x09
]

# Reverse lookup: name → index
STATIC_LOOKUP = {name: idx for idx, name in enumerate(STATIC_TABLE)}

# Marker byte indicating that a literal (non-indexed) header name follows
LITERAL_NAME_MARKER = 0xFF

# Known frame types (used for the skip-unknown rule)
_KNOWN_TYPES = frozenset({TYPE_REQUEST, TYPE_RESPONSE})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MalformedFrameError(Exception):
    """Raised when a received frame violates the protocol."""
    pass


# ---------------------------------------------------------------------------
# Frame data structure
# ---------------------------------------------------------------------------

class Frame:
    """Represents a single BHTP frame (request or response)."""

    __slots__ = ("frame_type", "flags", "status", "headers", "body")

    def __init__(self, frame_type, flags, status, headers, body):
        self.frame_type = frame_type      # int  (TYPE_REQUEST or TYPE_RESPONSE)
        self.flags      = flags           # int  (bitmask)
        self.status     = status          # int  (0 for requests, HTTP code for responses)
        self.headers    = list(headers)   # list of (name: str, value: str)
        self.body       = bytes(body)     # raw body bytes

    def get_header(self, name):
        """Return the value of the first header with the given name, or None."""
        for n, v in self.headers:
            if n == name:
                return v
        return None

    def __repr__(self):
        type_str = {TYPE_REQUEST: "REQUEST", TYPE_RESPONSE: "RESPONSE"}.get(
            self.frame_type, f"0x{self.frame_type:02X}"
        )
        return (
            f"Frame(type={type_str}, flags=0x{self.flags:02X}, "
            f"status={self.status}, headers={self.headers!r}, "
            f"body={len(self.body)} bytes)"
        )


# ---------------------------------------------------------------------------
# Header encoding / decoding  (HPACK-lite)
# ---------------------------------------------------------------------------

def encode_headers(headers):
    """Encode a list of (name, value) tuples into BHTP header bytes.

    For each header:
      - If the name is in STATIC_TABLE → write 1-byte index
      - Otherwise → write 0xFF + 2-byte name length + name bytes
      - Then always: 2-byte value length (big-endian) + value bytes
    """
    parts = []
    for name, value in headers:
        value_bytes = value.encode("utf-8")

        if name in STATIC_LOOKUP:
            # Indexed header name
            parts.append(struct.pack("!B", STATIC_LOOKUP[name]))
        else:
            # Literal header name
            name_bytes = name.encode("utf-8")
            parts.append(struct.pack("!B", LITERAL_NAME_MARKER))
            parts.append(struct.pack("!H", len(name_bytes)))
            parts.append(name_bytes)

        # Value is always length-prefixed
        parts.append(struct.pack("!H", len(value_bytes)))
        parts.append(value_bytes)

    return b"".join(parts)


def decode_headers(data, count):
    """Decode *count* header entries from *data*.

    Returns (headers, bytes_consumed) where headers is a list of
    (name, value) tuples.
    """
    headers = []
    offset = 0

    for i in range(count):
        # --- Name ---
        if offset >= len(data):
            raise MalformedFrameError(
                f"Header block truncated: expected header {i+1}/{count}"
            )

        name_idx = data[offset]
        offset += 1

        if name_idx == LITERAL_NAME_MARKER:
            # Literal name: 2-byte length + bytes
            if offset + 2 > len(data):
                raise MalformedFrameError("Truncated literal header name length")
            name_len = struct.unpack_from("!H", data, offset)[0]
            offset += 2
            if offset + name_len > len(data):
                raise MalformedFrameError("Truncated literal header name data")
            name = data[offset : offset + name_len].decode("utf-8")
            offset += name_len
        elif name_idx < len(STATIC_TABLE):
            # Indexed name from the static table
            name = STATIC_TABLE[name_idx]
        else:
            raise MalformedFrameError(
                f"Invalid header name index: 0x{name_idx:02X} "
                f"(valid range: 0x00–0x{len(STATIC_TABLE)-1:02X} or 0xFF)"
            )

        # --- Value (always length-prefixed) ---
        if offset + 2 > len(data):
            raise MalformedFrameError("Truncated header value length")
        value_len = struct.unpack_from("!H", data, offset)[0]
        offset += 2
        if offset + value_len > len(data):
            raise MalformedFrameError("Truncated header value data")
        value = data[offset : offset + value_len].decode("utf-8")
        offset += value_len

        headers.append((name, value))

    return headers, offset


# ---------------------------------------------------------------------------
# Frame encoding / decoding
# ---------------------------------------------------------------------------

def encode_frame(frame):
    """Serialize a Frame into its wire-format bytes.

    Returns the complete byte string: 9-byte header + payload.
    """
    header_bytes = encode_headers(frame.headers)
    payload = header_bytes + frame.body
    payload_length = len(payload)

    if payload_length > 0xFFFFFF:
        raise ValueError(
            f"Payload too large: {payload_length} bytes (max 16,777,215)"
        )
    if len(frame.headers) > 255:
        raise ValueError(
            f"Too many headers: {len(frame.headers)} (max 255)"
        )

    # Build the 9-byte frame header manually (24-bit length is awkward
    # with struct.pack, so we use a bytearray).
    hdr = bytearray(FRAME_HEADER_SIZE)
    hdr[0] = (payload_length >> 16) & 0xFF   # Length [23:16]
    hdr[1] = (payload_length >>  8) & 0xFF   # Length [15:8]
    hdr[2] =  payload_length        & 0xFF   # Length [7:0]
    hdr[3] =  frame.frame_type      & 0xFF   # Type
    hdr[4] =  frame.flags           & 0xFF   # Flags
    hdr[5] = (frame.status >>  8)   & 0xFF   # Status [15:8]
    hdr[6] =  frame.status          & 0xFF   # Status [7:0]
    hdr[7] =  len(frame.headers)    & 0xFF   # Header Count
    hdr[8] =  0x00                            # Reserved

    return bytes(hdr) + payload


def _recv_exact(sock, n):
    """Read exactly *n* bytes from *sock*.

    Returns None if the connection closes cleanly before any byte is read.
    Raises MalformedFrameError if the connection closes mid-read.
    """
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            if len(buf) == 0:
                return None          # clean close at a frame boundary
            raise MalformedFrameError(
                f"Connection closed after {len(buf)}/{n} bytes"
            )
        buf.extend(chunk)
    return bytes(buf)


def decode_frame(sock):
    """Read one BHTP frame from *sock*.

    Returns
    -------
    (Frame, raw_bytes) on success.
    (None, b"")        on a clean connection close.

    Raises
    ------
    MalformedFrameError  on any protocol violation.

    Unknown frame types are silently consumed (payload is read and
    discarded) and the function loops to read the next frame.  This
    implements the mandatory forward-compatibility rule.
    """
    while True:
        # ---- Read the 9-byte frame header ----
        hdr_data = _recv_exact(sock, FRAME_HEADER_SIZE)
        if hdr_data is None:
            return None, b""

        payload_length = (hdr_data[0] << 16) | (hdr_data[1] << 8) | hdr_data[2]
        frame_type     = hdr_data[3]
        flags          = hdr_data[4]
        status         = (hdr_data[5] << 8) | hdr_data[6]
        header_count   = hdr_data[7]
        # hdr_data[8] is reserved — ignored on read

        # ---- Read the payload ----
        if payload_length > 0:
            payload = _recv_exact(sock, payload_length)
            if payload is None:
                raise MalformedFrameError("Connection closed mid-payload")
        else:
            payload = b""

        raw = hdr_data + payload

        # ---- The Mandatory Rule ----
        # A receiver meeting a frame type it does not know MUST skip it
        # cleanly.  We have already consumed its payload above, so we
        # simply loop to the next frame.
        if frame_type not in _KNOWN_TYPES:
            continue

        # ---- Decode headers ----
        headers, headers_size = decode_headers(payload, header_count)

        # Everything after the headers in the payload is the body
        body = payload[headers_size:]

        return Frame(frame_type, flags, status, headers, body), raw


# ---------------------------------------------------------------------------
# Hexdump utility
# ---------------------------------------------------------------------------

def hexdump(data, prefix=""):
    """Format *data* as a traditional hex + ASCII dump.

    Example output (with prefix=">> "):
        >> 00000000  00 00 1a 01 01 00 00 05 00 00 03 47 45 54 01 00  |...........GET..|
        >> 00000010  0b 2f 69 6e 64 65 78 2e 68 74 6d 6c              |./index.html|
    """
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_part  = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{prefix}{offset:08x}  {hex_part:<48s}  |{ascii_part}|")
    if not lines:
        lines.append(f"{prefix}(empty)")
    return "\n".join(lines)
