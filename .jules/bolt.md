## 2025-05-18 - MD5 Hex String Conversion vs Direct Byte Parsing in Token Hash Tricks

**Learning:** Calling `hashlib.md5(...).hexdigest()` and then `int(..., 16)` inside token loops introduces significant string allocation and hex parsing overhead. Using `int.from_bytes(hashlib.md5(...).digest(), 'big')` produces the mathematically identical integer index directly from raw digest bytes. Combining this with `collections.Counter` to aggregate duplicate tokens before hashing yields ~13x speedup on hash vector calculations. Also learned that Python's native `str.count` in C can outperform Python `Counter` loops for string scanning on text, so always benchmark C-extensions vs Python iteration before replacing `str.count`.

**Action:** In token-level hash tricks or embeddings, aggregate unique token frequencies first and use `int.from_bytes(digest, 'big')` instead of string formatting (`hexdigest()`) and parsing (`int(..., 16)`).
