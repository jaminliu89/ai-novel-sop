## 2025-05-15 - [Python Hashing & N-Gram Generation Bottlenecks]
**Learning:**
1. Using `hashlib.md5(..).hexdigest()` with `int(..., 16)` inside token loops for feature hashing introduces massive CPU overhead due to hex string formatting and big-integer parsing. Replacing with `zlib.crc32(token.encode('utf-8'))` and `Counter` aggregation provides a ~4.8x speedup while preserving deterministic vector positions.
2. In n-gram repetition detection, generating intermediate list of tuple slices (`[tuple(tokens[i:i+n]) ...]`) incurs large heap allocation overhead. Streaming generator-based `zip(*(tokens[i:] for i in range(n)))` directly into `set(...)` speeds up `repetition_rate` by ~2.6x.

**Action:**
Use `zlib.crc32` / `Counter` for deterministic character/token feature hashing and `zip(*(tokens[i:] for i in range(n)))` generator streams for n-gram calculations in Python text processing pipelines.
