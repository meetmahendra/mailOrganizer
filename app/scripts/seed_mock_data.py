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

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))

from app.database import SessionLocal, engine
from app.models import Base, Email, EmailTag
from app.services.ai_service import get_email_tags
import datetime

def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    mock_email_text = "Hi, can we reschedule our meeting to tomorrow at 2 PM? It's quite urgent."
    
    print("Testing AI tagging on mock email...")
    tags = get_email_tags(mock_email_text)
    print(f"Generated tags: {tags.model_dump()}")
    
    # Store in DB
    new_email = Email(
        gmail_id="mock_id_124",
        subject="Reschedule Meeting",
        sender="client@example.com",
        snippet="Hi, can we reschedule...",
        body=mock_email_text
    )
    db.add(new_email)
    db.commit()
    db.refresh(new_email)
    
    new_tag = EmailTag(
        email_id=new_email.id,
        primary_intent=tags.primary_intent,
        context_tags=tags.context_tags,
        urgency_rating=tags.urgency_rating,
        suggested_action=tags.suggested_action
    )
    db.add(new_tag)
    db.commit()
    print("Mock data seeded successfully!")
    
if __name__ == "__main__":
    run()
