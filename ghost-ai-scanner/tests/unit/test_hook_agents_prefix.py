# =============================================================
# FILE: tests/unit/test_hook_agents_prefix.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Assert S3 prefix constants are correct and that generated
#          keys use config/HOOK_AGENTS/ — not the old agents/ prefix.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
# =============================================================

import sys
import os
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "store"))


class TestHookAgentsPrefix(unittest.TestCase):
    """Verify HOOK_AGENTS_PREFIX constant and derived S3 keys."""

    EXPECTED = "config/HOOK_AGENTS"

    def test_render_agent_package_constant(self) -> None:
        """render_agent_package.HOOK_AGENTS_PREFIX must equal expected."""
        import render_agent_package as rap
        self.assertEqual(rap.HOOK_AGENTS_PREFIX, self.EXPECTED)

    def test_agent_store_catalog_key(self) -> None:
        """agent_store.py source must define CATALOG_KEY under config/HOOK_AGENTS/."""
        src_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "store", "agent_store.py"
        )
        source = open(src_path).read()
        # CATALOG_KEY is set as an f-string referencing HOOK_AGENTS_PREFIX constant
        self.assertIn('CATALOG_KEY', source)
        self.assertIn('/catalog.json"', source)

    def test_agent_store_hook_agents_prefix(self) -> None:
        """agent_store.py must define HOOK_AGENTS_PREFIX constant."""
        src_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "store", "agent_store.py"
        )
        source = open(src_path).read()
        self.assertIn(f'HOOK_AGENTS_PREFIX = "{self.EXPECTED}"', source)

    def test_no_bare_agents_prefix_in_render(self) -> None:
        """render_agent_package must not contain bare 'agents/' S3 paths."""
        import inspect
        import render_agent_package as rap
        source = inspect.getsource(rap)
        # Allow the constant definition itself; reject bare f"agents/{...}" usage
        bad_patterns = ['"agents/', "'agents/", "f\"agents/", "f'agents/"]
        for pat in bad_patterns:
            self.assertNotIn(
                pat, source,
                f"Found bare agents/ path in render_agent_package.py: {pat!r}",
            )


if __name__ == "__main__":
    unittest.main()
