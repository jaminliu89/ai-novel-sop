import unittest
import asyncio
import os
from ai_novel.orchestrator import Orchestrator, Phase, Action

class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        os.environ["AI_NOVEL_MOCK"] = "1"
        self.config = {
            "llm_mode": "mock",
            "storage": {"chroma_path": ":memory:"}
        }

    def test_orchestrator_initialization(self):
        orchestrator = Orchestrator(config=self.config, book_id="test_book_001")
        self.assertEqual(orchestrator.current_phase, Phase.P1_WORLDVIEW)
        self.assertEqual(orchestrator.current_action, Action.DIVERGE)

    def test_concept_candidates_generation(self):
        orchestrator = Orchestrator(config=self.config, book_id="test_book_002")
        result = asyncio.run(orchestrator.generate_concept_candidates())
        self.assertIn("candidates", result)
        self.assertGreaterEqual(len(result["candidates"]), 1)

if __name__ == "__main__":
    unittest.main()
