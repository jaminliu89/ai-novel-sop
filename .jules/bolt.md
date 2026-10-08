## 2026-03-31 - Optimizing Chinese Text Quality Metrics & Voice Fingerprint Computation
**Learning:** `jieba.cut` creates Python generator state machines that incur overhead when converted to list (`list(jieba.cut)`). `jieba.lcut` executes C/CPython list creation directly. Additionally, generating n-grams via tuple slices in list comprehensions (`[tuple(tokens[i:i+n]) ...]`) creates heavy list slicing overhead compared to `zip(*(tokens[i:] for i in range(n)))`, which achieves a 57%+ speedup.
**Action:** Use `jieba.lcut` and `zip` iterators for n-gram generation and pre-compile combined regex patterns for forbidden word density checks.

## 2026-03-31 - Caching Pre-segmented Documents in TF-IDF Vector Retrieval
**Learning:** Re-segmenting corpus documents with `jieba` on every query in TF-IDF retrieval causes massive CPU bottlenecks (O(N_docs * query_count) repeated segmentation calls). Caching pre-segmented token strings (`_seg_doc`) directly on corpus items yields a >50x speedup for repeated TF-IDF queries.
**Action:** Always cache document segmentation results on corpus entry dictionaries when performing text retrieval or vector search fallback.
