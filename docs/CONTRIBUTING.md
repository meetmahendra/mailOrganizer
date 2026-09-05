# Developer Contribution Guidelines

Thank you for your interest in contributing to the Email Organizer project! To maintain code quality, ensure security compliance, and streamline audits, we ask all contributors to follow these guidelines.

---

## 🤝 Code of Conduct

* Be respectful and professional in all communications.
* Ensure code changes focus on security, safety, and human-in-the-loop guardrails.

---

## 🛠️ Code and Development Standards

To keep the codebase maintainable, we adhere to standard Python conventions:

* **PEP 8 Compliance**: Write clean, readable code. Use 4 spaces for indentation.
* **Type Hints**: Use type annotations for function signatures and class definitions.
* **Docstrings**: Document all new modules, classes, and functions using Google-style docstrings:
  ```python
  def example_function(param1: int, param2: str) -> bool:
      """Brief summary of the function's purpose.

      Args:
          param1: Explanation of param1.
          param2: Explanation of param2.

      Returns:
          True if successful, False otherwise.
      """
  ```
* **No Hardcoded Secrets**: Never hardcode API keys, passwords, or tokens. Always use environment variables loaded via `dotenv`.

---

## 🚀 Pull Request Workflow

### Step 1: Create a Branch
Use descriptive branch names prefixing the type of change:
* `feature/` for new functionality (e.g., `feature/outlook-adapter`)
* `bugfix/` for bug fixes (e.g., `bugfix/quota-error-handling`)
* `docs/` for documentation changes (e.g., `docs/add-api-endpoints`)

### Step 2: License Headers (Crucial)
Every new `.py` file must contain the Apache License 2.0 copyright header at the top of the file:
```python
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
```

### Step 3: Run Local Syntax & Synthetic Quality Gate Checks
1. Configure Git pre-push hooks (one-time setup):
   ```bash
   python setup_hooks.py
   ```
2. Run local syntax checks:
   ```bash
   python -m py_compile app/pipeline/nodes.py app/main.py
   ```
3. Run the comprehensive 550-scenario synthetic test suite:
   ```bash
   python run_tests.py --quality-gate
   ```
   This generates interactive statistical reports in `reports/report.html` and verifies 100% compliance on VIP safeguards, no-reply suppression, and classification accuracy.

### Step 4: Submit a Pull Request
Ensure your pull request includes:
1. A clear description of the problem solved.
2. Link to the issue or ticket (if applicable).
3. Verification results (logs, test runs, or CLI output screenshots from `run_tests.py`).
4. An update in the [Changelog](CHANGELOG.md) under the `[Unreleased]` section.

By contributing to this project, you agree that your contributions will be licensed under the project's Apache License 2.0 terms.
