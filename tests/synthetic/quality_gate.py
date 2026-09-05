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
Quality Gate Threshold Validator.

Enforces strict pass/fail gates before code integration or Git push:
  1. 100% VIP Safety Compliance (0 VIP archives/trashes permitted)
  2. 100% No-Reply Draft Suppression (0 drafts planned for automated senders)
  3. Minimum Classification Accuracy >= 90%
  4. Maximum Urgency Score MAE <= 1.25
"""
from typing import Dict, Any, Tuple


class QualityGateValidator:

    def __init__(
        self,
        min_accuracy: float = 0.90,
        max_urgency_mae: float = 1.25,
        enforce_zero_vip_violations: bool = True,
        enforce_zero_noreply_violations: bool = True,
    ):
        self.min_accuracy = min_accuracy
        self.max_urgency_mae = max_urgency_mae
        self.enforce_zero_vip = enforce_zero_vip_violations
        self.enforce_zero_noreply = enforce_zero_noreply_violations

    def evaluate(self, stats: Dict[str, Any]) -> Tuple[bool, list[str]]:
        """
        Evaluate stats against thresholds. Returns (passed: bool, failure_reasons: list[str]).
        """
        reasons = []
        cm = stats.get("confusion_matrix", {})
        accuracy = cm.get("overall_accuracy", 0.0)
        safety = stats.get("safety_compliance", {})
        urg = stats.get("urgency_metrics", {})
        mae = urg.get("mae", 0.0)

        # 1. VIP Inviolability Check
        vip_violations = safety.get("vip_violations", [])
        if self.enforce_zero_vip and vip_violations:
            reasons.append(f"[FAIL] VIP Safety Violation: {len(vip_violations)} VIP email(s) were scheduled for archiving/deletion: {vip_violations[:5]}")

        # 2. No-Reply Draft Suppression Check
        noreply_violations = safety.get("no_reply_violations", [])
        if self.enforce_zero_noreply and noreply_violations:
            reasons.append(f"[FAIL] No-Reply Draft Violation: {len(noreply_violations)} automated email(s) had drafts scheduled: {noreply_violations[:5]}")

        # 3. Accuracy Threshold
        if accuracy < self.min_accuracy:
            reasons.append(f"[FAIL] Accuracy Threshold Breach: Overall Accuracy {accuracy*100:.1f}% is below required {self.min_accuracy*100:.1f}%")

        # 4. Urgency MAE Threshold
        if mae > self.max_urgency_mae:
            reasons.append(f"[FAIL] Urgency MAE Breach: Urgency MAE {mae:.2f} exceeds threshold {self.max_urgency_mae:.2f}")

        passed = len(reasons) == 0
        return passed, reasons
