## 2025-03-08 - Candidate Pairwise Operations in Quality Metrics
**Learning:** In fallback metrics calculation like `_jaccard_diversity`, pairwise comparisons repeatedly call tokenization and n-gram set creation ($O(N^2)$ times).
**Action:** Precompute per-candidate sets/features in $O(N)$ before entering pairwise comparison loops.
