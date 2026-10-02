## 2026-03-31 - Optimizing Chinese Text Quality Metrics & Voice Fingerprint Computation
**Learning:** `jieba.cut` creates Python generator state machines that incur overhead when converted to list (`list(jieba.cut)`). `jieba.lcut` executes C/CPython list creation directly. Additionally, generating n-grams via tuple slices in list comprehensions (`[tuple(tokens[i:i+n]) ...]`) creates heavy list slicing overhead compared to `zip(*(tokens[i:] for i in range(n)))`, which achieves a 57%+ speedup.
**Action:** Use `jieba.lcut` and `zip` iterators for n-gram generation and pre-compile combined regex patterns for forbidden word density checks.

## 2026-03-31 - Vectorized Semantic Diversity & Pre-computed Candidate N-Grams
**Learning:** In pairwise candidate similarity metrics (e.g. Jaccard & Embedding diversity), evaluating candidate $i$ against candidate $j$ inside $O(N^2)$ nested loops recomputes candidate $i$'s tokenization and n-gram set $N-1$ times, causing heavy redundant CPU overhead. For embeddings, scalar dot products and vector norms inside nested Python loops incur high interpreter overhead compared to vectorized matrix multiplication (`np.dot(normalized, normalized.T)`).
**Action:** Pre-compute $O(N)$ n-gram sets or embeddings before pairwise iteration, and use numpy matrix operations for pairwise metric calculations to achieve 5.5x to 12x speedups.
