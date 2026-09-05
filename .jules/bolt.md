## 2025-05-18 - Fast n-gram extraction via iterator zipping

**Learning:** Using list comprehension with per-element slice and tuple creation `[tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]` creates overhead due to repetitive list slicing and Python loop iterations. Replacing it with `list(zip(*(tokens[i:] for i in range(n))))` delegates slice offset binding to C-level `zip` iteration, resulting in >2x performance improvement (~2.17x faster) on n-gram computations used heavily in `repetition_rate`, `ngram_jaccard`, and Jaccard diversity metrics.

**Action:** Prefer `zip(*(seq[i:] for i in range(n)))` over index-range slicing list comprehensions when generating overlapping n-grams from lists or tokens.
