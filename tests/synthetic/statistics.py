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
Statistical Evaluation Engine.

Computes comprehensive mathematical, machine learning, and QA metrics:
  • 9x9 Confusion Matrix & Per-Category Precision / Recall / F1
  • Urgency Score MAE, RMSE, and error distribution
  • Reply Necessity classification metrics (ROC / Precision / Recall)
  • VIP & Safety Safeguard compliance (100% inviolability verification)
  • Departmental & Hierarchy-level breakdown performance
  • Latency & throughput percentiles (p50, p90, p95, p99)
"""
import math
from typing import List, Dict, Any
from tests.synthetic.schema import TestResult

VALID_CATEGORIES = [
    "Action Required (High)",
    "Action Required (Med/Low)",
    "Calendar/Scheduling",
    "Informational/Logs",
    "Receipts/Financial",
    "Promotions/Marketing",
    "Spam/Trash",
    "System Alert",
    "Needs Review",
]


def compute_confusion_matrix(results: List[TestResult]) -> Dict[str, Any]:
    """Compute 9x9 confusion matrix and per-class classification metrics."""
    matrix = {actual: {pred: 0 for pred in VALID_CATEGORIES} for actual in VALID_CATEGORIES}
    
    for r in results:
        actual = r.expected.category if r.expected.category in VALID_CATEGORIES else "Needs Review"
        pred = r.predicted_category if r.predicted_category in VALID_CATEGORIES else "Needs Review"
        matrix[actual][pred] += 1

    per_class = {}
    total_samples = len(results)
    correct_samples = 0

    for cat in VALID_CATEGORIES:
        tp = matrix[cat][cat]
        fp = sum(matrix[other][cat] for other in VALID_CATEGORIES if other != cat)
        fn = sum(matrix[cat][other] for other in VALID_CATEGORIES if other != cat)
        tn = total_samples - (tp + fp + fn)

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        support = sum(matrix[cat].values())
        correct_samples += tp

        per_class[cat] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "support": support,
        }

    overall_accuracy = (correct_samples / total_samples) if total_samples > 0 else 0.0
    active_classes = [c for c in per_class.values() if c["support"] > 0]
    macro_f1 = (sum(c["f1_score"] for c in active_classes) / len(active_classes)) if active_classes else 0.0
    weighted_f1 = (sum(c["f1_score"] * c["support"] for c in active_classes) / total_samples) if total_samples > 0 else 0.0

    return {
        "matrix": matrix,
        "categories": VALID_CATEGORIES,
        "per_class": per_class,
        "overall_accuracy": round(overall_accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "total_samples": total_samples,
        "correct_samples": correct_samples,
    }


def compute_urgency_statistics(results: List[TestResult]) -> Dict[str, Any]:
    """Compute Mean Absolute Error (MAE), RMSE, and distribution of urgency errors."""
    if not results:
        return {}

    abs_errors = []
    sq_errors = []
    exact_matches = 0
    within_one = 0
    within_two = 0
    major_errors = 0

    for r in results:
        exp_range = r.expected.urgency_score_range or [1, 10]
        pred_urg = r.predicted_urgency or 5
        
        # Distance to closest point in expected range
        if pred_urg < exp_range[0]:
            diff = exp_range[0] - pred_urg
        elif pred_urg > exp_range[1]:
            diff = pred_urg - exp_range[1]
        else:
            diff = 0

        abs_errors.append(diff)
        sq_errors.append(diff ** 2)

        if diff == 0:
            exact_matches += 1
        elif diff == 1:
            within_one += 1
        elif diff == 2:
            within_two += 1
        else:
            major_errors += 1

    n = len(results)
    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "exact_match_rate": round(exact_matches / n, 4),
        "within_one_rate": round((exact_matches + within_one) / n, 4),
        "within_two_rate": round((exact_matches + within_one + within_two) / n, 4),
        "distribution": {
            "exact (0 diff)": exact_matches,
            "off_by_1": within_one,
            "off_by_2": within_two,
            "off_by_3_plus": major_errors,
        },
    }


def compute_reply_necessity_statistics(results: List[TestResult]) -> Dict[str, Any]:
    """Compute binary classification metrics for reply necessity."""
    tp, fp, fn, tn = 0, 0, 0, 0
    for r in results:
        exp = bool(r.expected.is_reply_necessary)
        pred = bool(r.predicted_reply_necessary)
        if exp and pred:
            tp += 1
        elif not exp and pred:
            fp += 1
        elif exp and not pred:
            fn += 1
        else:
            tn += 1

    total = len(results)
    acc = ((tp + tn) / total) if total > 0 else 0.0
    prec = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    rec = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    spec = (tn / (tn + fp)) if (tn + fp) > 0 else 0.0

    return {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1_score": round(f1, 4),
        "specificity": round(spec, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def compute_safety_compliance_statistics(results: List[TestResult]) -> Dict[str, Any]:
    """
    Evaluate strict zero-violation safety guardrails:
      - 100% VIP emails must be kept in Inbox with @VIP (zero archive/trash)
      - 100% No-Reply emails must have draft creation suppressed
    """
    vip_count = 0
    vip_protected = 0
    vip_archive_violations = []

    no_reply_count = 0
    no_reply_draft_suppressed = 0
    no_reply_draft_violations = []

    for r in results:
        # Check VIP safety
        if r.expected.is_vip or r.predicted_is_vip:
            vip_count += 1
            has_blocked_action = any(
                a.get("action") in ("remove_inbox", "safe_archive", "move_to_trash")
                for a in r.predicted_actions
            )
            has_vip_label = any(
                a.get("action") == "apply_label" and a.get("label") == "@VIP"
                for a in r.predicted_actions
            )
            if not has_blocked_action and has_vip_label:
                vip_protected += 1
            else:
                vip_archive_violations.append(r.test_id)

        # Check No-Reply draft suppression
        if r.expected.is_no_reply or r.predicted_is_no_reply:
            no_reply_count += 1
            has_draft_reply = any(
                a.get("action") == "create_draft_reply"
                for a in r.predicted_actions
            )
            if not has_draft_reply:
                no_reply_draft_suppressed += 1
            else:
                no_reply_draft_violations.append(r.test_id)

    vip_rate = (vip_protected / vip_count) if vip_count > 0 else 1.0
    no_reply_rate = (no_reply_draft_suppressed / no_reply_count) if no_reply_count > 0 else 1.0

    return {
        "vip_total_tested": vip_count,
        "vip_protected": vip_protected,
        "vip_compliance_rate": round(vip_rate, 4),
        "vip_violations": vip_archive_violations,
        "no_reply_total_tested": no_reply_count,
        "no_reply_suppressed": no_reply_draft_suppressed,
        "no_reply_compliance_rate": round(no_reply_rate, 4),
        "no_reply_violations": no_reply_draft_violations,
        "passed_safety_gate": len(vip_archive_violations) == 0 and len(no_reply_draft_violations) == 0,
    }


def compute_department_statistics(results: List[TestResult]) -> Dict[str, Any]:
    """Compute breakdown metrics grouped by business domain / department."""
    dept_map = {}
    for r in results:
        domain = r.domain or "General"
        if domain not in dept_map:
            dept_map[domain] = {
                "total": 0,
                "passed": 0,
                "category_matches": 0,
                "urgency_matches": 0,
                "durations_ms": [],
            }
        d = dept_map[domain]
        d["total"] += 1
        if r.passed:
            d["passed"] += 1
        if r.category_match:
            d["category_matches"] += 1
        if r.urgency_match:
            d["urgency_matches"] += 1
        d["durations_ms"].append(r.duration_ms)

    summary = {}
    for dom, d in dept_map.items():
        n = d["total"]
        summary[dom] = {
            "total_cases": n,
            "pass_rate": round(d["passed"] / n, 4) if n > 0 else 0.0,
            "category_accuracy": round(d["category_matches"] / n, 4) if n > 0 else 0.0,
            "urgency_accuracy": round(d["urgency_matches"] / n, 4) if n > 0 else 0.0,
            "avg_latency_ms": round(sum(d["durations_ms"]) / n, 2) if n > 0 else 0.0,
        }
    return summary


def compute_latency_statistics(results: List[TestResult]) -> Dict[str, Any]:
    """Compute latency distribution and percentiles (p50, p90, p95, p99)."""
    if not results:
        return {}
    durations = sorted([r.duration_ms for r in results])
    n = len(durations)

    def percentile(p):
        idx = int(math.ceil((p / 100.0) * n)) - 1
        return durations[max(0, min(idx, n - 1))]

    return {
        "total_runtime_s": round(sum(durations) / 1000.0, 2),
        "mean_ms": round(sum(durations) / n, 2),
        "median_p50_ms": round(percentile(50), 2),
        "p90_ms": round(percentile(90), 2),
        "p95_ms": round(percentile(95), 2),
        "p99_ms": round(percentile(99), 2),
        "min_ms": round(durations[0], 2),
        "max_ms": round(durations[-1], 2),
    }


def generate_evaluation_summary(results: List[TestResult]) -> Dict[str, Any]:
    """Assemble all statistical and QA metrics into a master evaluation payload."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    return {
        "summary": {
            "total_tests": total,
            "passed_tests": passed,
            "failed_tests": failed,
            "overall_pass_rate": round((passed / total), 4) if total > 0 else 0.0,
        },
        "confusion_matrix": compute_confusion_matrix(results),
        "urgency_metrics": compute_urgency_statistics(results),
        "reply_necessity_metrics": compute_reply_necessity_statistics(results),
        "safety_compliance": compute_safety_compliance_statistics(results),
        "department_metrics": compute_department_statistics(results),
        "latency_metrics": compute_latency_statistics(results),
    }
