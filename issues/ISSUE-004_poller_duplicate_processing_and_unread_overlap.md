# ISSUE-004: Poller Duplicate Reprocessing, Unread Overlap & Non-Chronological Ingestion

| Metadata | Details |
|---|---|
| **Issue ID** | `ISSUE-004` |
| **Title** | Poller Duplicate Reprocessing, Unread Overlap & Non-Chronological Ingestion |
| **Status** | Open / Planned for Implementation |
| **Severity** | Critical (Infinite Reprocessing Loop, LLM Quota Exhaustion, Out-of-Order Execution) |
| **Component** | Polling Worker ([`app/scripts/poll_worker.py`](file:///d:/mailOrganizer/app/scripts/poll_worker.py)), Gmail Service ([`app/services/gmail_service.py`](file:///d:/mailOrganizer/app/services/gmail_service.py)), Ingestion Routes ([`app/routes/emails.py`](file:///d:/mailOrganizer/app/routes/emails.py)) |
| **Date Logged** | 2026-09-12 |

---

## 1. Problem Description

The background polling worker ([`app/scripts/poll_worker.py`](file:///d:/mailOrganizer/app/scripts/poll_worker.py)) runs on a fixed interval (`POLL_INTERVAL=60s`). On every cycle, it fetches a fixed batch of unread emails (`max_results=20`) via `fetch_unread_emails(creds, max_results=20)` and executes the full LangGraph pipeline for each message.

However, the poller is **completely stateless, lacks deduplication, and does not enforce causal chronological ordering**:

1. **Infinite Reprocessing of Lingering Unread Emails (Batch Overlapping)**:
   - By design in [`config/rules/defaults.yaml`](file:///d:/mailOrganizer/config/rules/defaults.yaml), categories such as `Action Required (High)`, `Action Required (Med/Low)`, and `Calendar/Scheduling` **do not** include `mark_as_read` because the human user needs to see them as unread in their email client.
   - In `DRY_RUN` mode (the default), zero Gmail mutations occur, leaving 100% of emails marked as `UNREAD`.
   - On the next cycle (60 seconds later), `fetch_unread_emails` queries `labelIds=['INBOX', 'UNREAD']` and returns the same unread emails.
   - The poller re-executes `run_pipeline()` for all of them, triggering duplicate LLM classifications, connector queries, draft generations, database inserts into `EmailProcessingLog`, and duplicate rows in `audit_log.csv`.

2. **Partial Overlap and Query Limit Behavior (e.g. 5 New Emails vs. 20 Limit)**:
   - When asked for `maxResults=20`, the Gmail API returns matching messages in **reverse chronological order** (newest to oldest).
   - If 20 unread emails were processed in Batch 1 and left unread, and subsequently **5 new emails arrive**, a simple `messages.list(maxResults=20)` returns the **5 brand-new emails PLUS the 15 newest emails from the previous batch** to fill the requested quota of 20.
   - Without a query-level filter, 15 emails are needlessly re-processed.

3. **Queue Starvation for New Emails**:
   - Because `fetch_unread_emails` currently retrieves only the first `max_results=20` messages without a timestamp high-water mark or exclusion query, a mailbox with $\ge 20$ unread emails will cause the poller to remain permanently stuck on those 20. Any newly arriving 21st or subsequent email is starved and never processed.

4. **Non-Chronological Ingestion Order**:
   - Gmail API returns messages reverse-chronologically or in thread activity order.
   - Processing incoming emails in reverse or arbitrary order breaks multi-turn thread coherence: a reply from a sender might be processed *before* their initial question, causing the LLM to hallucinate or misjudge conversation state.

---

## 2. Root Cause Analysis (RCA)

### Bottleneck 1: Stateless Polling Loop in `app/scripts/poll_worker.py`
In [`app/scripts/poll_worker.py`](file:///d:/mailOrganizer/app/scripts/poll_worker.py#L58-L84):
```python
def process_user(user: User, db, dry_run: bool) -> None:
    ...
    creds      = credentials_from_json(user.credentials_json)
    raw_emails = fetch_unread_emails(creds, max_results=20)
    print(f"  [{user.email}] {len(raw_emails)} unread email(s) found.")

    for e in raw_emails:
        final_state = run_pipeline(
            email_data = e,
            creds      = creds,
            user_id    = user.id,
            dry_run    = dry_run,
        )
```
- There is no comparison between the current poll batch and the previous poll batch (`new_emails = current_batch - last_batch`).
- There is no check against previously processed `gmail_id`s in SQLite (`EmailProcessingLog` or `Email`).

### Bottleneck 2: Missing Query Boundaries in `fetch_unread_emails()`
In [`app/services/gmail_service.py`](file:///d:/mailOrganizer/app/services/gmail_service.py#L64-L68):
```python
result = service.users().messages().list(
    userId='me',
    labelIds=['INBOX', 'UNREAD'],
    maxResults=max_results,
).execute()
```
- The query lacks an `after:{epoch_seconds}` parameter or `-label:...` exclusion marker. It relies solely on `labelIds=['INBOX', 'UNREAD']`, causing older, already-processed unread emails to be returned repeatedly.

### Bottleneck 3: Unsorted Message Execution
- `fetch_unread_emails` iterates through `messages` exactly as returned by `messages().list()`.
- It does not extract the Gmail `internalDate` (epoch milliseconds) and does not sort messages. As a result, emails arrive at the pipeline in reverse chronological or arbitrary order.

---

## 3. Query Architecture: Returning Only Truly New Emails

### Q&A: Does Gmail API return the newest 20 if asked for 20?
**Yes.** `messages.list(maxResults=20)` returns the 20 newest matching messages (descending order). However, if only 5 new emails exist alongside 20 older unread ones, Gmail returns the **5 new + 15 old** emails.

### Solution: Query Configuration for Zero Overlap
To instruct Gmail to return **only the 5 new emails and 0 older ones** (even when `maxResults=20`), the query must be bounded at the API level:

#### Primary Approach: Unix Epoch Timestamp High-Water Mark (`after:{epoch_seconds}`)
Gmail supports seconds-level epoch timestamps in the search parameter `q`:
```python
# Query Gmail only for unread inbox emails received AFTER the last processed message
query = f"in:inbox is:unread after:{last_processed_timestamp_epoch}"

result = service.users().messages().list(
    userId='me',
    q=query,
    maxResults=max_results,
).execute()
```
- **Mechanism**:
  1. Every Gmail message payload contains an `internalDate` header (epoch milliseconds when Gmail accepted the message).
  2. When an email is processed, the system records `last_processed_epoch = int(msg['internalDate']) // 1000`.
  3. On the next cycle, passing `after:{last_processed_epoch}` ensures Gmail's index **strictly excludes** all emails received at or prior to that second.
  4. If only 5 new emails have arrived, Gmail returns **only those 5 emails** (the result list contains 5 items, not 20).

#### Secondary Approach: Server-Side Exclusion Label (`-label:_Processed`)
```python
query = "in:inbox is:unread -label:_MailOrganizer/Processed"
```
- **Mechanism**:
  1. After the pipeline processes an email, it applies a system label `_MailOrganizer/Processed`.
  2. The query automatically ignores any email possessing that label, regardless of its `UNREAD` or `INBOX` status.
  3. If 5 new emails arrive, only those 5 lack the label; Gmail returns exactly those 5.

---

## 4. Current vs. Expected Behavior

| Dimension | Current Pipeline Behavior | Expected Pipeline Behavior |
|---|---|---|
| **Batch Overlap** | Poller repeatedly returns the same 20 unread emails every 60 seconds | **Zero overlap**: Only fetches and processes emails not previously processed |
| **Search Window** | Scans all unread emails indefinitely | **High-Water Mark**: Searches only for unread emails newer than the last processed checkpoint (`after:{timestamp}`) |
| **Mailbox Scope** | Relies solely on `labelIds=['INBOX', 'UNREAD']` | Strictly enforces **INBOX only** (`in:inbox is:unread`), ignoring spam, promotions outside inbox, or archives |
| **Processing Order** | Arbitrary or reverse-chronological order | **Strict Chronological Order**: Sorted by `internalDate` ascending (oldest unprocessed to newest) so conversation turns are handled in causal sequence |
| **New Email Starvation** | If 20 unread emails linger, new unread emails are blocked | Poller bounds search to new emails, guaranteeing immediate ingestion of new arrivals |
| **Resource Consumption** | Redundant LLM token burn and duplicate drafts every 60s | Zero redundant LLM calls; clean 1:1 execution per email |

---

## 5. Proposed Implementation Plan

### Step 1: High-Water Mark & State Tracking
1. **Persistent Checkpoint**:
   - Add `last_processed_internal_date` (epoch ms) to `users` table or a dedicated `sync_checkpoints` table.
   - Before querying Gmail, retrieve the user's latest checkpoint:
     ```python
     last_epoch_sec = (user.last_processed_internal_date // 1000) if user.last_processed_internal_date else None
     ```
2. **Dynamic Query Construction in `app/services/gmail_service.py`**:
   ```python
   def fetch_unread_emails(
       creds: Credentials,
       max_results: int = 20,
       after_epoch_seconds: Optional[int] = None,
   ) -> List[dict]:
       query = "in:inbox is:unread"
       if after_epoch_seconds:
           query += f" after:{after_epoch_seconds}"

       result = service.users().messages().list(
           userId='me',
           q=query,
           maxResults=max_results,
       ).execute()
   ```

### Step 2: Extract `internalDate` and Sort Chronologically
In [`app/services/gmail_service.py`](file:///d:/mailOrganizer/app/services/gmail_service.py):
1. Extract `internalDate` when retrieving each message:
   ```python
   raw = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
   internal_date = int(raw.get('internalDate', 0))
   ```
2. Sort the batch chronologically (oldest-first) before returning:
   ```python
   emails.sort(key=lambda m: m['internal_date'])
   ```
3. Update checkpoint after successful processing:
   ```python
   user.last_processed_internal_date = max(user.last_processed_internal_date or 0, email['internal_date'])
   db.commit()
   ```

### Step 3: Local Database Deduplication Safety Gate
In [`app/scripts/poll_worker.py`](file:///d:/mailOrganizer/app/scripts/poll_worker.py):
- Even with Gmail `after:` filters, handle edge cases (e.g. multiple emails received within the same second) by verifying that `email['gmail_id']` is not already recorded in `EmailProcessingLog`:
  ```python
  processed_ids = {row[0] for row in db.query(EmailProcessingLog.gmail_id).all()}
  new_emails = [e for e in raw_emails if e['gmail_id'] not in processed_ids]
  ```

### Step 4: Endpoint Alignment in `app/routes/emails.py`
- Update `POST /emails/ingest` to respect `skip_processed=True` and utilize the chronological pipeline flow.

### Step 5: Verification & Automated Tests
1. **Chronological Order Test (`tests/test_gmail_ordering.py`)**:
   - Mock Gmail returning 3 messages out of order (`[turn_3, turn_1, turn_2]`).
   - Verify that `fetch_unread_emails` returns them in exact ascending order (`[turn_1, turn_2, turn_3]`).
2. **Quota & Bounded Query Test (`tests/test_poll_worker.py`)**:
   - Mock 20 previously processed unread emails and 5 new unread emails.
   - Verify that passing `after:{epoch}` returns only the 5 new emails despite `max_results=20`.
   - Verify that Cycle 2 executes 0 pipeline runs when no new emails arrive.
