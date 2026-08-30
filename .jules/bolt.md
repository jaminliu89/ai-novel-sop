## 2026-08-30 - Eager initialization of jieba dictionary in AI novel pipeline
**Learning:** `jieba` tokenization performs lazy dictionary loading by default on the first `jieba.cut()` invocation, introducing an ~1.4s latency spike during initial request handling in `QualityMetrics`.
**Action:** Call `jieba.initialize()` eagerly at module import time within `try...except ImportError` blocks to move dictionary loading to startup time.
