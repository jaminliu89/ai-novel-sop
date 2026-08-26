# Bolt's Journal - Critical Learnings

## 2025-05-18 - Fast Token Hashing & N-Gram Generation
**Learning:** Using `hashlib.md5` for hashing tokens into vector dimensions creates heavy string formatting and 128-bit integer parsing overhead inside hot loops. Replacing it with `zlib.crc32` achieves a ~3.8x speedup. In addition, using `zip(*[tokens[i:] for i in range(n)])` for n-gram generation eliminates intermediate list slicing comprehensions, yielding a ~2.8x speedup.
**Action:** Use `zlib.crc32` for fast deterministic feature hashing in fallback vector spaces, and `zip` iterator unpacking for n-gram tuple creation.
