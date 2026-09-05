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

import os.path
import base64
from email.message import EmailMessage
import google.generativeai as genai
from dotenv import load_dotenv

from google.auth.transport.requests import Request

load_dotenv()
if os.getenv('GEMINI_API_KEY'):
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.readonly',
]

def get_service():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def extract_email_text(payload):
    text = ""
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data')
                if data:
                    text += base64.urlsafe_b64decode(data).decode('utf-8')
            elif 'parts' in part:
                text += extract_email_text(part)
    else:
        # Sometimes the body is directly in payload for simple text emails
        data = payload.get('body', {}).get('data')
        if data:
            text += base64.urlsafe_b64decode(data).decode('utf-8')
    return text

def main():
    service = get_service()
    if not service:
        return

    print("Checking for unread messages...")
    try:
        # Get unread messages in INBOX
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD']).execute()
        messages = results.get('messages', [])

        if not messages:
            print('No unread messages found.')
            return

        print(f"Found {len(messages)} unread message(s).")
        for msg in messages:
            msg_id = msg['id']
            # Fetch message details
            message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            
            headers = message['payload']['headers']
            subject = ''
            sender = ''
            msg_id_header = ''
            
            for header in headers:
                if header['name'] == 'Subject':
                    subject = header['value']
                elif header['name'] == 'From':
                    sender = header['value']
                elif header['name'] == 'Message-ID':
                    msg_id_header = header['value']
            
            print("="*40)
            print(f"From: {sender}")
            print(f"Subject: {subject}")
            
            email_body = extract_email_text(message['payload'])
            
            print("\nGenerating reply using LLM...")
            try:
                model = genai.GenerativeModel('gemini-flash-latest')
                prompt = f"Please draft a polite and professional reply to this email. Here is the email:\n\nSubject: {subject}\nFrom: {sender}\n\n{email_body}"
                response = model.generate_content(prompt)
                reply_text = response.text.strip()
            except Exception as e:
                print(f"Failed to generate LLM reply (make sure GEMINI_API_KEY is set in .env): {e}")
                reply_text = "Hello, \n\nThank you for your email. I have received it and will get back to you shortly if needed.\n\nBest regards."
            
            print("\nDrafted Reply:")
            print("-" * 20)
            print(reply_text)
            print("-" * 20)
            
            action = input("Do you want to send this reply? (y: send / n: mark read without sending / s: skip / e: exit): ").strip().lower()
            
            if action == 'y':
                send_reply(service, sender, subject, reply_text, msg_id_header, msg_id)
                print("Reply sent.")
            elif action == 'n':
                # Mark as read
                service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
                print("Message marked as read.")
            elif action == 'e':
                print("Exiting application...")
                return
            else:
                print("Skipped.")
                
    except HttpError as error:
        print(f'An error occurred: {error}')

def send_reply(service, to_address, original_subject, reply_text, message_id_header, thread_id):
    try:
        message = EmailMessage()
        message.set_content(reply_text)

        message['To'] = to_address
        message['From'] = 'me'
        if original_subject.startswith('Re:') or original_subject.startswith('RE:'):
            message['Subject'] = original_subject
        else:
            message['Subject'] = f'Re: {original_subject}'
            
        if message_id_header:
            message['In-Reply-To'] = message_id_header
            message['References'] = message_id_header

        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {
            'raw': encoded_message,
            'threadId': thread_id
        }

        service.users().messages().send(userId="me", body=create_message).execute()
        
        # Remove UNREAD label from original message
        service.users().messages().modify(userId='me', id=thread_id, body={'removeLabelIds': ['UNREAD']}).execute()

    except HttpError as error:
        print(f'An error occurred while sending reply: {error}')

if __name__ == '__main__':
    main()
