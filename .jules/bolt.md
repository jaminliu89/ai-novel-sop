## 2026-03-31 - Optimizing Chinese Text Quality Metrics & Voice Fingerprint Computation
**Learning:** `jieba.cut` creates Python generator state machines that incur overhead when converted to list (`list(jieba.cut)`). `jieba.lcut` executes C/CPython list creation directly. Additionally, generating n-grams via tuple slices in list comprehensions (`[tuple(tokens[i:i+n]) ...]`) creates heavy list slicing overhead compared to `zip(*(tokens[i:] for i in range(n)))`, which achieves a 57%+ speedup.
**Action:** Use `jieba.lcut` and `zip` iterators for n-gram generation and pre-compile combined regex patterns for forbidden word density checks.

## 2026-03-31 - Single-pass Counter Sum for Fixed Character Feature Sets
**Learning:** Iterating through string constants in Python to check string lengths and invoke `text.count(p)` or fallback logic creates unnecessary CPU loop iterations and string search overhead when all characters in the target set are single-character tokens.
**Action:** Directly sum counts from a single pre-calculated `collections.Counter(text)` mapping (e.g. `sum(counts[p] for p in _PUNCTUATION_ALL)`), avoiding redundant multi-pass `str.count` calls.
