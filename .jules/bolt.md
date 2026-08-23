# Bolt's Journal

## 2025-05-18 - Zip Generator vs Slice List Comprehension for N-Grams
**Learning:** Constructing n-grams via `list(zip(*(tokens[i:] for i in range(n))))` leverages C-level iteration in Python's `zip` built-in, outperforming Python-level list slicing in comprehensions (`[tuple(tokens[i : i + n]) ...]`) by ~2.8x.
**Action:** Use generator expression with `zip` for tuple sliding windows over sequences in performance-critical NLP/text processing routines.
