## 2026-03-31 - Optimizing Chinese Text Quality Metrics & Voice Fingerprint Computation
**Learning:** `jieba.cut` creates Python generator state machines that incur overhead when converted to list (`list(jieba.cut)`). `jieba.lcut` executes C/CPython list creation directly. Additionally, generating n-grams via tuple slices in list comprehensions (`[tuple(tokens[i:i+n]) ...]`) creates heavy list slicing overhead compared to `zip(*(tokens[i:] for i in range(n)))`, which achieves a 57%+ speedup.
**Action:** Use `jieba.lcut` and `zip` iterators for n-gram generation and pre-compile combined regex patterns for forbidden word density checks.

## 2026-03-31 - Clarification on `jieba.lcut` & Precomputing Pairwise Metric Inputs
**Learning:** In `jieba`, `lcut` is implemented as `return list(cut(*args, **kwargs))`. It does not perform C-level list creation directly, so wrapping `jieba.lcut` inside a generator or list comprehension adds unnecessary intermediate list allocations.
For pairwise $O(N^2)$ candidate metric calculations (e.g. Jaccard diversity), re-tokenizing and building n-gram sets in the inner loop executes $N(N-1)$ tokenizations. Precomputing $N$ n-gram sets upfront reduces overhead from $O(N^2)$ to $O(N)$ tokenizations, achieving a >95% speedup.
**Action:** Precompute token/n-gram sets before nested pairwise evaluation loops rather than inside inner loop calls.
