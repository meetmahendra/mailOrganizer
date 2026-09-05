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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import User
from services.auth_service import credentials_from_json
from services.ai_service import translate_query_to_gmail
from services.gmail_service import execute_gmail_search

router = APIRouter()


class SearchQuery(BaseModel):
    query: str
    user_id: int = 1
    max_results: int = 10


@router.post("/")
def hybrid_search(payload: SearchQuery, db: Session = Depends(get_db)):
    """
    Translate a natural language search query into a Gmail search string using AI,
    then execute it against the Gmail API and return matching emails.
    """
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user or not user.credentials_json:
        raise HTTPException(status_code=401, detail="User not authenticated. Visit /auth/login first.")

    creds = credentials_from_json(user.credentials_json)

    # Step 1: AI translates the natural query to a Gmail search string
    gmail_query = translate_query_to_gmail(payload.query)

    # Step 2: Execute the Gmail search
    results = execute_gmail_search(creds, gmail_query, max_results=payload.max_results)

    return {
        "original_query": payload.query,
        "gmail_query": gmail_query,
        "result_count": len(results),
        "results": results,
    }
