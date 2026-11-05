"""
app/task_parser.py
------------------
Natural language task parser combining Python regular expressions and the
`dateparser` library to extract structured task attributes from informal text.

Supported Natural Language Syntax:
- Due Dates: 'today', 'tomorrow', 'next Friday', '5 Nov', 'in 3 days', 'by 15 Dec', etc.
- Priority: 'high priority', 'low priority', 'medium priority', 'priority: high', '!high', 'p1'/'p2'/'p3', 'urgent'.
- Assignee: '@username' or '@firstname' (e.g. '@ravi', '@sarah', '@alex').
- Importance: the keyword 'important' or 'urgent & important' or '⭐'.
- Title: the remaining text after cleanly removing the matched metadata tokens.
"""

import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import dateparser
from dateparser.search import search_dates

# -------------------------------------------------------------------------
# Regex Definitions
# -------------------------------------------------------------------------

# 1. Importance Regex: matches word 'important', 'urgent & important', or star emoji
IMPORTANT_REGEX = re.compile(
    r'(?i)(?:\bimportant\b|\burgent\s*&\s*important\b|⭐)',
    re.IGNORECASE
)

# 2. Priority Regex: matches various forms of priority specification
PRIORITY_REGEX = re.compile(
    r'(?i)(?:'
    r'\b((?:high|medium|low))\s+priority\b|'
    r'\bpriority[:=\s\-]+((?:high|medium|low))\b|'
    r'(?:^|\s)!((?:high|medium|low|p1|p2|p3))\b|'
    r'\b(p1|p2|p3)\b|'
    r'\b(urgent)\b'
    r')'
)

# 3. Assignee Regex: matches @username / @name handles
ASSIGNEE_REGEX = re.compile(r'(?:^|\s)@([a-zA-Z0-9_\.\-]+)')

# 4. Due Date Regex Patterns: common relative, weekday, and explicit date forms
DATE_SUB_PATTERNS = [
    # Explicit dates: '5 Nov', '5th Nov', 'Nov 5', 'November 5th', '5 Nov 2026'
    r'\b(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+\d{2,4})?)\b',
    r'\b(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*\d{2,4})?)\b',
    # Numeric ISO / formatted dates: 2026-11-05, 05/11/2026, 11-05-2026
    r'\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b',
    # Relative day words: today, tomorrow, day after tomorrow, tonight
    r'\b(?:day\s+after\s+tomorrow|tomorrow|today|tonight)\b',
    # Relative offset: in 2 days, in 3 weeks, in 1 month
    r'\b(?:in\s+\d+\s+(?:days?|weeks?|months?|hours?))\b',
    # Weekdays: 'next Friday', 'this monday', 'coming tuesday', 'Wednesday'
    r'\b(?:(?:next|this|coming)\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    # General ranges: 'next week', 'end of week'
    r'\b(?:next\s+week|end\s+of\s+(?:this\s+)?week)\b'
]

COMBINED_DATE_REGEX = re.compile(
    r'(?:\b(?:due|by|on|before)\s+)?(' + '|'.join(DATE_SUB_PATTERNS) + r')',
    re.IGNORECASE
)


def _parse_date_with_smart_fallback(date_expr: str, now: datetime) -> Optional[datetime]:
    """
    Parses a date expression using dateparser, intelligently choosing between
    current period and future preference so that today's date (e.g. '5 Nov' on Nov 5)
    and upcoming weekdays are resolved accurately.
    """
    try:
        dt_future = dateparser.parse(
            date_expr,
            settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': now}
        )
        dt_current = dateparser.parse(
            date_expr,
            settings={'PREFER_DATES_FROM': 'current_period', 'RELATIVE_BASE': now}
        )

        if dt_current and dt_current.date() == now.date():
            return dt_current
        if dt_current and dt_current.date() > now.date():
            return dt_current
        return dt_future or dt_current
    except Exception:
        return None


def parse_quick_task(raw_text: str, users: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """
    Parses a natural language task sentence and extracts title, due date, priority,
    assignee, and importance flag.

    Args:
        raw_text: Informal input string, e.g. "Finish report tomorrow high priority @ravi important"
        users: Optional list of user dicts [{'id': ..., 'name': ..., 'email': ...}] for matching

    Returns:
        dict containing parsed structured fields, or None if raw_text is empty.
    """
    if not raw_text or not raw_text.strip():
        return None

    working_text = raw_text.strip()
    spans_to_remove = []
    now = datetime.now()

    # ---------------------------------------------------------------------
    # 1. Parse Importance
    # ---------------------------------------------------------------------
    important = False
    imp_match = IMPORTANT_REGEX.search(working_text)
    if imp_match:
        important = True
        spans_to_remove.append((imp_match.start(), imp_match.end()))

    # ---------------------------------------------------------------------
    # 2. Parse Priority
    # ---------------------------------------------------------------------
    priority = 'medium'
    priority_raw = None
    p_match = PRIORITY_REGEX.search(working_text)
    if p_match:
        # Extract whichever capture group succeeded
        val = next((g for g in p_match.groups() if g is not None), '').lower()
        if val in ('p1', 'urgent'):
            priority = 'high'
        elif val == 'p2':
            priority = 'medium'
        elif val == 'p3':
            priority = 'low'
        elif val in ('high', 'medium', 'low'):
            priority = val
        priority_raw = p_match.group(0).strip()
        spans_to_remove.append((p_match.start(), p_match.end()))

    # ---------------------------------------------------------------------
    # 3. Parse Assignee (@handle)
    # ---------------------------------------------------------------------
    assignee_id = None
    assignee_name = None
    assignee_raw = None
    assignee_found = False

    a_match = ASSIGNEE_REGEX.search(working_text)
    if a_match:
        handle = a_match.group(1).strip()
        assignee_raw = f"@{handle}"
        spans_to_remove.append((a_match.start(), a_match.end()))

        if users:
            handle_lower = handle.lower()
            # Priority 1: Exact full name match (case-insensitive, spaces ignored)
            for u in users:
                u_name = u.get('name', '')
                if u_name.lower() == handle_lower or u_name.lower().replace(' ', '') == handle_lower:
                    assignee_id = u.get('id')
                    assignee_name = u_name
                    assignee_found = True
                    break

            # Priority 2: First name match (e.g. '@ravi' matches 'Ravi Patel')
            if not assignee_found:
                for u in users:
                    u_name = u.get('name', '')
                    parts = u_name.lower().split()
                    if parts and parts[0] == handle_lower:
                        assignee_id = u.get('id')
                        assignee_name = u_name
                        assignee_found = True
                        break

            # Priority 3: Email prefix match (e.g. '@sarah' matches 'sarah@example.com')
            if not assignee_found:
                for u in users:
                    u_email = u.get('email', '')
                    prefix = u_email.lower().split('@')[0]
                    if prefix == handle_lower or prefix.replace('.', '') == handle_lower:
                        assignee_id = u.get('id')
                        assignee_name = u.get('name')
                        assignee_found = True
                        break

            # Priority 4: Substring match
            if not assignee_found:
                for u in users:
                    if handle_lower in u.get('name', '').lower():
                        assignee_id = u.get('id')
                        assignee_name = u.get('name')
                        assignee_found = True
                        break

        # Fallback to handle name if not registered in user table
        if not assignee_name:
            assignee_name = handle

    # ---------------------------------------------------------------------
    # 4. Parse Due Date (Regex + dateparser)
    # ---------------------------------------------------------------------
    due_date = None
    due_date_human = None
    due_date_raw = None

    d_match = COMBINED_DATE_REGEX.search(working_text)
    if d_match:
        full_match_str = d_match.group(0)
        date_expr = d_match.group(1)
        parsed_dt = _parse_date_with_smart_fallback(date_expr, now)

        if parsed_dt:
            due_date = parsed_dt.date().isoformat()
            due_date_raw = full_match_str.strip()
            spans_to_remove.append((d_match.start(), d_match.end()))

            # Format human friendly label
            p_date = parsed_dt.date()
            now_date = now.date()
            if p_date == now_date:
                due_date_human = f"Today ({parsed_dt.strftime('%b %d')})"
            elif p_date == (now_date + timedelta(days=1)):
                due_date_human = f"Tomorrow ({parsed_dt.strftime('%b %d')})"
            elif p_date.year == now_date.year:
                due_date_human = parsed_dt.strftime('%a, %b %d')
            else:
                due_date_human = parsed_dt.strftime('%b %d, %Y')

    # Secondary search_dates fallback if regex didn't trigger
    if not due_date:
        try:
            # Mask already matched non-date tokens
            temp_text = working_text
            for start, end in sorted(spans_to_remove, key=lambda s: s[0], reverse=True):
                temp_text = temp_text[:start] + (' ' * (end - start)) + temp_text[end:]

            sd = search_dates(
                temp_text,
                settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': now}
            )
            if sd:
                matched_snippet, dt = sd[0]
                # Filter out pure digits, single letters, or short non-date tokens
                clean_snippet = matched_snippet.strip()
                if len(clean_snippet) > 2 and not clean_snippet.isdigit():
                    due_date = dt.date().isoformat()
                    due_date_raw = clean_snippet
                    p_date = dt.date()
                    now_date = now.date()
                    if p_date == now_date:
                        due_date_human = f"Today ({dt.strftime('%b %d')})"
                    elif p_date == (now_date + timedelta(days=1)):
                        due_date_human = f"Tomorrow ({dt.strftime('%b %d')})"
                    else:
                        due_date_human = dt.strftime('%a, %b %d')

                    # Remove matched snippet from working_text
                    m_idx = working_text.lower().find(matched_snippet.lower())
                    if m_idx != -1:
                        spans_to_remove.append((m_idx, m_idx + len(matched_snippet)))
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # 5. Extract and Clean Task Title
    # ---------------------------------------------------------------------
    clean_chars = list(working_text)
    for start, end in sorted(spans_to_remove, key=lambda s: s[0], reverse=True):
        clean_chars[start:end] = [' '] * (end - start)

    clean_title = re.sub(r'\s+', ' ', ''.join(clean_chars)).strip(' ,.-_–—:')
    if not clean_title:
        clean_title = 'Untitled Task'

    return {
        'title': clean_title,
        'due_date': due_date,
        'due_date_human': due_date_human,
        'due_date_raw': due_date_raw,
        'priority': priority,
        'priority_label': priority.capitalize(),
        'priority_raw': priority_raw,
        'important': important,
        'assignee_id': assignee_id,
        'assignee_name': assignee_name,
        'assignee_raw': assignee_raw,
        'assignee_found': assignee_found,
        'raw_text': raw_text
    }
