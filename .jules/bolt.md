## 2025-05-18 - Hash Vector & NLP Feature Extraction Optimization

**Learning:** In fallback NLP pipelines (such as `VoiceProfile._hash_vector`), tokenizing text and hashing tokens character by character with `hexdigest()` and `int(..., 16)` inside a loop causes redundant MD5 operations and slow string conversions for duplicate tokens. By aggregating token counts first using `collections.Counter`, MD5 hashing and byte conversions are only performed once per unique token, yielding a ~7.5x speedup (e.g. 34.7s -> 4.6s for 1000 runs) while outputting identical hash vectors. Furthermore, pre-compiling sentence-splitting regex patterns avoids re-parsing regex expressions on every metric evaluation.

**Action:** Always aggregate duplicate items using `collections.Counter` before performing expensive per-item operations like hashing, and pre-compile regular expressions used in hot paths.
