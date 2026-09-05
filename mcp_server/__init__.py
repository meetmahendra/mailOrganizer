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
Gmail Organizer MCP Server Package.

Transport : SSE (HTTP + Server-Sent Events) on port 8001
Auth      : Assumes user_id=1 with credentials stored via FastAPI /auth/login
Safety    : All mutating tools default dry_run=True
"""
