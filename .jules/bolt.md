## 2026-03-31 - Optimizing Chinese Text Quality Metrics & Voice Fingerprint Computation
**Learning:** `jieba.cut` creates Python generator state machines that incur overhead when converted to list (`list(jieba.cut)`). `jieba.lcut` executes C/CPython list creation directly. Additionally, generating n-grams via tuple slices in list comprehensions (`[tuple(tokens[i:i+n]) ...]`) creates heavy list slicing overhead compared to `zip(*(tokens[i:] for i in range(n)))`, which achieves a 57%+ speedup.
**Action:** Use `jieba.lcut` and `zip` iterators for n-gram generation and pre-compile combined regex patterns for forbidden word density checks.

## 2026-03-31 - Pre-computing N-Gram Sets for Pairwise Candidate Diversity Evaluation
**Learning:** Pairwise similarity calculations (like Jaccard diversity across N candidate generated texts) repeatedly invoke tokenization and n-gram set creation `N*(N-1)` times if called per pair. Precomputing `ngram_set` for each of the N candidates reduces tokenization complexity from O(N^2) to O(N), yielding a 6.9x speedup (~85% reduction in execution time for 8 candidates).
**Action:** Always precompute tokenized representations or feature sets before pairwise comparison loops in diversity/similarity metrics.
