# Copyright 2026 Mahendra GURAV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit Tests for Chained Thread and Non-Chained Topic History Services.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))

from services.history_context_service import _clean_quoted_text, format_history_context_block


class TestHistoryContext(unittest.TestCase):

    def test_clean_quoted_text(self):
        """Verify email quotes and reply markers are stripped cleanly."""
        raw_body = "Hi David, I have updated the rate limits.\n\nOn Mon, Aug 31, 2026 at 9:00 AM David Chen wrote:\n> Can we get an update?"
        cleaned = _clean_quoted_text(raw_body)
        self.assertNotIn("On Mon, Aug 31", cleaned)
        self.assertIn("I have updated the rate limits", cleaned)

    def test_format_history_context_block(self):
        """Verify multi-turn history block formatting."""
        turns = [
            {"turn": 1, "date": "2026-08-28", "sender": "David Chen", "snippet": "Need rate limit increase."},
            {"turn": 2, "date": "2026-08-28", "sender": "Arjun Mehta", "snippet": "Looking into it."},
        ]
        memories = [
            {"date": "2026-08-15", "subject": "Tier-2 Contract", "category": "Receipts/Financial", "urgency": 4, "reasoning": "Contract signed"}
        ]
        block = format_history_context_block(turns, memories)
        self.assertIn("Chained Thread Timeline", block)
        self.assertIn("Turn 1", block)
        self.assertIn("Tier-2 Contract", block)


if __name__ == "__main__":
    unittest.main()
