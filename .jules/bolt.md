# Bolt's Journal - Critical Learnings

## 2026-09-03 - Avoid O(N^2) repeated tokenization in candidate pairwise comparisons
**Learning:** In candidate comparison metrics (such as `_jaccard_diversity` or candidate pairwise evaluation), computing metrics per pair by invoking functions that tokenize the text redundantly causes $O(N^2)$ tokenization overhead. Pre-computing candidate representation sets in $O(N)$ once before comparing candidate pairs reduces execution time by over 80%.
**Action:** Always pre-compute token/n-gram sets or embeddings once per candidate before running pairwise comparison loops.
