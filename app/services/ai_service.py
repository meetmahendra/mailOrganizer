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

import os
from pydantic import BaseModel
from typing import List
from google import genai


class EmailTagSchema(BaseModel):
    primary_intent: str
    context_tags: List[str]
    urgency_rating: str      # Low / Medium / High / Critical
    suggested_action: str


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment.")
    return genai.Client(api_key=api_key)



def get_email_tags(subject: str, sender: str, body: str) -> EmailTagSchema:
    """
    Call Gemini with a structured output schema to classify an email
    into intent, tags, urgency, and suggested action.
    """
    try:
        client = _get_client()
        prompt = (
            "You are an intelligent email classifier. "
            "Analyze the email below and return ONLY structured JSON with:\n"
            "- primary_intent: one concise category (e.g. Meeting Request, Invoice, Support Ticket)\n"
            "- context_tags: 2-3 short descriptive tags\n"
            "- urgency_rating: one of [Low, Medium, High, Critical]\n"
            "- suggested_action: one recommended action (e.g. Schedule meeting, Reply with quote, Archive)\n\n"
            f"Subject: {subject}\nFrom: {sender}\n\n{body}"
        )
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': EmailTagSchema,
            },
        )
        return response.parsed
    except Exception as e:
        print(f"AI tagging error: {e}")
        return EmailTagSchema(
            primary_intent="Uncategorized",
            context_tags=[],
            urgency_rating="Low",
            suggested_action="Review manually",
        )


def translate_query_to_gmail(natural_query: str) -> str:
    """
    Use Gemini to convert a natural language search query into a
    Gmail search string (e.g. from:boss@co.com after:2024/01/01).
    """
    try:
        client = _get_client()
        prompt = (
            "Convert the following natural language email search query into a "
            "valid Gmail search operator string. Return ONLY the Gmail search string, nothing else.\n\n"
            f"Query: {natural_query}"
        )
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
        )
        return response.text.strip().strip('"').strip("'")
    except Exception as e:
        print(f"Query translation error: {e}")
        return natural_query
