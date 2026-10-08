# Annotated Hexdump — BHTP Request & Response

**Exchange:** `GET /hello.txt` → `200 OK` (13-byte body: `Hello, BHTP!\n`)

---

## Request Frame (63 bytes total)

```
Offset    Hex                                               ASCII
--------  ------------------------------------------------  ----------------
00000000  00 00 36 01 01 00 00 05 00 00 00 03 47 45 54 01   ..6.........GET.
00000010  00 0a 2f 68 65 6c 6c 6f 2e 74 78 74 02 00 0e 6c   ../hello.txt...l
00000020  6f 63 61 6c 68 6f 73 74 3a 39 30 30 30 08 00 03   ocalhost:9000...
00000030  2a 2f 2a 09 00 09 62 63 75 72 6c 2f 31 2e 30      */*...bcurl/1.0
```

### Frame Header (bytes 0–8)

| Offset | Bytes         | Field          | Decoded Value                          |
|--------|---------------|----------------|----------------------------------------|
| 0–2    | `00 00 36`    | Payload Length | **54** (0x000036 = 54 bytes after header) |
| 3      | `01`          | Frame Type     | **0x01 = REQUEST**                      |
| 4      | `01`          | Flags          | **0x01 = END_STREAM** (no more requests) |
| 5–6    | `00 00`       | Status Code    | **0** (unused in requests)              |
| 7      | `05`          | Header Count   | **5** headers follow                    |
| 8      | `00`          | Reserved       | `0x00` (must be zero)                   |

### Header Block (bytes 9–62)

#### Header 1: `:method` = `GET`
| Offset | Bytes            | Field       | Decoded                           |
|--------|------------------|-------------|-----------------------------------|
| 9      | `00`             | Name Index  | **0x00** → `:method` (static table) |
| 10–11  | `00 03`          | Value Length | **3** bytes                        |
| 12–14  | `47 45 54`       | Value Data  | **`GET`**                          |

#### Header 2: `:path` = `/hello.txt`
| Offset | Bytes                        | Field       | Decoded                           |
|--------|------------------------------|-------------|-----------------------------------|
| 15     | `01`                         | Name Index  | **0x01** → `:path` (static table)  |
| 16–17  | `00 0a`                      | Value Length | **10** bytes                       |
| 18–27  | `2f 68 65 6c 6c 6f 2e 74 78 74` | Value Data | **`/hello.txt`**                  |

#### Header 3: `:host` = `localhost:9000`
| Offset | Bytes                                    | Field       | Decoded                           |
|--------|------------------------------------------|-------------|-----------------------------------|
| 28     | `02`                                     | Name Index  | **0x02** → `:host` (static table)  |
| 29–30  | `00 0e`                                  | Value Length | **14** bytes                       |
| 31–44  | `6c 6f 63 61 6c 68 6f 73 74 3a 39 30 30 30` | Value Data | **`localhost:9000`**            |

#### Header 4: `accept` = `*/*`
| Offset | Bytes         | Field       | Decoded                           |
|--------|---------------|-------------|-----------------------------------|
| 45     | `08`          | Name Index  | **0x08** → `accept` (static table) |
| 46–47  | `00 03`       | Value Length | **3** bytes                        |
| 48–50  | `2a 2f 2a`    | Value Data  | **`*/*`**                          |

#### Header 5: `user-agent` = `bcurl/1.0`
| Offset | Bytes                           | Field       | Decoded                              |
|--------|---------------------------------|-------------|--------------------------------------|
| 51     | `09`                            | Name Index  | **0x09** → `user-agent` (static table)|
| 52–53  | `00 09`                         | Value Length | **9** bytes                           |
| 54–62  | `62 63 75 72 6c 2f 31 2e 30`    | Value Data  | **`bcurl/1.0`**                       |

### Body

No body in the request frame. All 54 payload bytes are consumed by the 5 headers.

---

## Response Frame (85 bytes total)

```
Offset    Hex                                               ASCII
--------  ------------------------------------------------  ----------------
00000000  00 00 4c 02 00 00 c8 04 00 03 00 0a 74 65 78 74   ..L.........text
00000010  2f 70 6c 61 69 6e 04 00 02 31 33 05 00 0a 62 73   /plain...13...bs
00000020  65 72 76 65 2f 31 2e 30 06 00 1d 53 75 6e 2c 20   erve/1.0...Sun,
00000030  30 34 20 4f 63 74 20 32 30 32 36 20 31 37 3a 30   04 Oct 2026 17:0
00000040  34 3a 33 34 20 47 4d 54 48 65 6c 6c 6f 2c 20 42   4:34 GMTHello, B
00000050  48 54 50 21 0a                                    HTP!.
```

### Frame Header (bytes 0–8)

| Offset | Bytes         | Field          | Decoded Value                           |
|--------|---------------|----------------|-----------------------------------------|
| 0–2    | `00 00 4c`    | Payload Length | **76** (0x00004C = 76 bytes after header) |
| 3      | `02`          | Frame Type     | **0x02 = RESPONSE**                      |
| 4      | `00`          | Flags          | **0x00** (no flags set)                  |
| 5–6    | `00 c8`       | Status Code    | **200** (0x00C8 = HTTP 200 OK)           |
| 7      | `04`          | Header Count   | **4** headers follow                     |
| 8      | `00`          | Reserved       | `0x00`                                   |

### Header Block (bytes 9–71)

#### Header 1: `content-type` = `text/plain`
| Offset | Bytes                                 | Field       | Decoded                                 |
|--------|---------------------------------------|-------------|----------------------------------------|
| 9      | `03`                                  | Name Index  | **0x03** → `content-type` (static table) |
| 10–11  | `00 0a`                               | Value Length | **10** bytes                             |
| 12–21  | `74 65 78 74 2f 70 6c 61 69 6e`       | Value Data  | **`text/plain`**                         |

#### Header 2: `content-length` = `13`
| Offset | Bytes      | Field       | Decoded                                    |
|--------|------------|-------------|-------------------------------------------|
| 22     | `04`       | Name Index  | **0x04** → `content-length` (static table)  |
| 23–24  | `00 02`    | Value Length | **2** bytes                                 |
| 25–26  | `31 33`    | Value Data  | **`13`**                                    |

#### Header 3: `server` = `bserve/1.0`
| Offset | Bytes                              | Field       | Decoded                              |
|--------|------------------------------------|-------------|--------------------------------------|
| 27     | `05`                               | Name Index  | **0x05** → `server` (static table)    |
| 28–29  | `00 0a`                            | Value Length | **10** bytes                          |
| 30–39  | `62 73 65 72 76 65 2f 31 2e 30`    | Value Data  | **`bserve/1.0`**                      |

#### Header 4: `date` = `Sun, 04 Oct 2026 17:04:34 GMT`
| Offset | Bytes                                                        | Field       | Decoded                          |
|--------|--------------------------------------------------------------|-------------|----------------------------------|
| 40     | `06`                                                         | Name Index  | **0x06** → `date` (static table)  |
| 41–42  | `00 1d`                                                      | Value Length | **29** bytes                      |
| 43–71  | `53 75 6e 2c 20 30 34 20 4f 63 74 20 32 30 32 36 ...`       | Value Data  | **`Sun, 04 Oct 2026 17:04:34 GMT`** |

### Body (bytes 72–84)

| Offset | Bytes                                       | Decoded               |
|--------|---------------------------------------------|-----------------------|
| 72–84  | `48 65 6c 6c 6f 2c 20 42 48 54 50 21 0a`   | **`Hello, BHTP!\n`**   |

The body is 13 bytes (matching `content-length: 13`). It begins immediately
after the last header entry and extends to the end of the payload.

---

## Verification

- **Request payload length:** 54 = 63 total − 9 header = 54 ✓
- **Response payload length:** 76 = 85 total − 9 header = 76 ✓
- **Response body:** 76 payload − 63 header bytes = 13 body bytes ✓
- **All header names used static table indices** (no literal names in this exchange)
- **Every byte is accounted for** — the spec is finished.
