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
External Rules Engine.

Loads action rules from:
  config/rules/defaults.yaml  — shipped defaults
  config/rules/overrides.yaml — user overrides (wins on conflict)

Merges the two at startup; the merged result is cached.
Overrides completely replace a category's action list (no partial merging).
"""
import os
import sys
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

_APP_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_DIR = os.path.normpath(os.path.join(_APP_DIR, '..', 'config', 'rules'))

_DEFAULTS_PATH  = os.path.join(_CONFIG_DIR, 'defaults.yaml')
_OVERRIDES_PATH = os.path.join(_CONFIG_DIR, 'overrides.yaml')

# Fallback ACTION_MAP used when YAML files are not available
_FALLBACK_MAP = {
    'Action Required (High)': [
        {'action': 'keep_inbox'},
        {'action': 'apply_label', 'label': '@Urgent'},
        {'action': 'star_thread'},
        {'action': 'create_draft_reply', 'if_reply_necessary': True},
    ],
    'Action Required (Med/Low)': [
        {'action': 'remove_inbox'},
        {'action': 'apply_label', 'label': '@Action_Required'},
        {'action': 'create_draft_reply', 'if_reply_necessary': True},
    ],
    'Calendar/Scheduling': [
        {'action': 'remove_inbox'},
        {'action': 'apply_label', 'label': '@Scheduling'},
        {'action': 'create_draft_reply', 'if_reply_necessary': True},
    ],
    'Informational/Logs': [
        {'action': 'remove_inbox'},
        {'action': 'apply_label', 'label': 'Log/Updates'},
        {'action': 'mark_as_read'},
    ],
    'Receipts/Financial': [
        {'action': 'remove_inbox'},
        {'action': 'apply_label', 'label': 'Finance/Receipts'},
        {'action': 'mark_as_read'},
    ],
    'Promotions/Marketing': [
        {'action': 'remove_inbox'},
        {'action': 'safe_archive', 'label': '_LLM/Promotions'},
        {'action': 'mark_as_read'},
    ],
    'Spam/Trash': [
        {'action': 'safe_archive', 'label': '_LLM/Suspected_Spam'},
        {'action': 'mark_as_read'},
    ],
    'System Alert': [
        {'action': 'keep_inbox'},
        {'action': 'apply_label', 'label': '@System_Alert'},
        {'action': 'create_user_task'},
    ],
    'Needs Review': [
        {'action': 'keep_inbox'},
        {'action': 'apply_label', 'label': '@Review_Needed'},
    ],
}

_merged_rules: Optional[dict] = None


def _load_yaml(path: str) -> dict:
    if yaml is None:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[rules_engine] Failed to load {path}: {e}")
        return {}


def _load_rules() -> dict:
    """Load and merge defaults + overrides. Cached after first call."""
    global _merged_rules
    if _merged_rules is not None:
        return _merged_rules

    defaults_data  = _load_yaml(_DEFAULTS_PATH)
    overrides_data = _load_yaml(_OVERRIDES_PATH)

    if not defaults_data:
        print("[rules_engine] WARNING: defaults.yaml not found. Using fallback rules.")
        _merged_rules = _FALLBACK_MAP
        return _merged_rules

    merged = dict(defaults_data.get('categories', {}))
    overrides = overrides_data.get('categories', {}) if overrides_data else {}
    for category, actions in overrides.items():
        merged[category] = actions
        print(f"[rules_engine] Override applied for category: '{category}'")

    _merged_rules = merged
    return _merged_rules


def reload_rules() -> None:
    """Force a reload of rules from YAML files (e.g. after file edit)."""
    global _merged_rules
    _merged_rules = None
    _load_rules()


def get_actions_for_category(category: str, state: dict) -> list:
    """
    Return the resolved action list for a given category,
    filtering out conditional actions that don't apply.

    Conditions evaluated:
      if_reply_necessary: true  — only include if state['is_reply_necessary'] is True
      if_pm_enabled: true       — only include if PM integration is enabled
    """
    rules = _load_rules()
    raw_actions = rules.get(category, rules.get('Informational/Logs', []))

    is_reply_necessary = state.get('is_reply_necessary', True)
    is_no_reply        = state.get('is_no_reply', False)
    pm_enabled         = _is_pm_enabled()

    resolved = []
    for action in raw_actions:
        action = dict(action)  # copy to avoid mutating cached config

        # Filter: if_reply_necessary
        if action.pop('if_reply_necessary', False) and (not is_reply_necessary or is_no_reply):
            continue

        # Filter: if_pm_enabled
        if action.pop('if_pm_enabled', False) and not pm_enabled:
            continue

        resolved.append(action)

    return resolved


def _is_pm_enabled() -> bool:
    """Check if PM integration is enabled via config."""
    pm_config_path = os.path.normpath(
        os.path.join(_APP_DIR, '..', 'config', 'integrations', 'pm_adapter.yaml')
    )
    data = _load_yaml(pm_config_path)
    return data.get('enabled', False)
