"""
app/api.py
----------
RESTful API blueprint for the TaskManager application.

This module provides standard JSON endpoints for CRUD operations on Tasks:
- POST   /api/tasks          -> Create a new task (Validates JSON body)
- GET    /api/tasks          -> List all tasks (Supports query filters for status, priority, etc.)
- GET    /api/tasks/<id>     -> Retrieve a single task by ID
- PUT    /api/tasks/<id>     -> Update an existing task (Full or partial updates)
- PATCH  /api/tasks/<id>     -> Partial update for an existing task
- DELETE /api/tasks/<id>     -> Delete a task by ID
- GET    /api/activity       -> Retrieve activity audit trail logs

Every mutation (create, update, delete) and retrieval is thoroughly validated and
logged into the ActivityLog database model.
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify
from flask_login import current_user
from app import db
from app.models import Task, User, ActivityLog, TimeLog, TaskChange, record_task_change, calculate_workload_summary

# Define the REST API Blueprint with URL prefix '/api'
api_bp = Blueprint('api', __name__, url_prefix='/api')


def get_acting_user_id(payload: dict = None) -> int:
    """
    Helper function to determine the user ID responsible for an API operation.
    Prioritizes:
    1. Authenticated session user (`current_user.id`) if logged in.
    2. Explicit `user_id` or `created_by` passed in the JSON payload or headers.
    3. First available registered User in the database as fallback.
    """
    if current_user and current_user.is_authenticated:
        return current_user.id

    if payload:
        explicit_id = payload.get('user_id') or payload.get('created_by')
        if explicit_id and User.query.get(explicit_id):
            return explicit_id

    # Check X-User-ID header (useful for API clients)
    header_user_id = request.headers.get('X-User-ID', type=int)
    if header_user_id and User.query.get(header_user_id):
        return header_user_id

    # Fallback to the first user in the database
    first_user = User.query.first()
    return first_user.id if first_user else None


def log_api_activity(action: str, task_id: int = None, user_id: int = None) -> ActivityLog:
    """
    Helper to record an API event in the ActivityLog table and commit to the database.
    Safely commits or rolls back without corrupting the session.

    Args:
        action (str): Description of the API action.
        task_id (int, optional): ID of the affected task.
        user_id (int, optional): ID of the user performing the action.

    Returns:
        ActivityLog or None: The newly created activity log record, or None on failure.
    """
    try:
        entry = ActivityLog(action=action, task_id=task_id, user_id=user_id)
        db.session.add(entry)
        db.session.commit()
        return entry
    except Exception:
        db.session.rollback()
        return None


def parse_due_date(date_str: str):
    """
    Validates and parses an ISO date string (YYYY-MM-DD).

    Returns:
        tuple (datetime.date or None, error_string or None)
    """
    if not date_str:
        return None, None
    try:
        parsed_date = datetime.strptime(str(date_str).strip(), '%Y-%m-%d').date()
        return parsed_date, None
    except ValueError:
        return None, "Field 'due_date' must be in 'YYYY-MM-DD' format."


# -------------------------------------------------------------------
# 1. CREATE Task (POST /api/tasks)
# -------------------------------------------------------------------

@api_bp.route('/tasks', methods=['POST'])
def api_create_task():
    """
    Create Task:
    Expects a JSON body with task details.

    Required fields:
        - title (str): Non-empty title, max 200 characters.

    Optional fields:
        - description (str): Additional task details.
        - status (str): One of ['todo', 'doing', 'done'] (default: 'todo').
        - priority (str): One of ['low', 'medium', 'high'] (default: 'medium').
        - due_date (str): Target date in 'YYYY-MM-DD' format.
        - assigned_to (int): Valid User ID of assignee.
        - created_by (int): Valid User ID of creator (defaults to current_user or first user).

    Returns:
        JSON response with status 201 on success or 400 on validation error.
    """
    # 1. Validate JSON header and body
    if not request.is_json:
        return jsonify({
            'success': False,
            'error': 'Request Content-Type must be application/json.'
        }), 400

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({
            'success': False,
            'error': 'Malformed JSON body.'
        }), 400

    # 2. Validate 'title'
    title = payload.get('title')
    if not title or not isinstance(title, str) or not title.strip():
        return jsonify({
            'success': False,
            'error': "Field 'title' is required and must be a non-empty string."
        }), 400

    title = title.strip()
    if len(title) > 200:
        return jsonify({
            'success': False,
            'error': "Field 'title' cannot exceed 200 characters."
        }), 400

    # 3. Validate 'description'
    description = payload.get('description', '')
    if description is not None and not isinstance(description, str):
        return jsonify({
            'success': False,
            'error': "Field 'description' must be a string."
        }), 400
    description = description.strip() if description else None

    # 4. Validate 'status'
    status = payload.get('status', 'todo')
    if not isinstance(status, str) or status.lower() not in ['todo', 'doing', 'done']:
        return jsonify({
            'success': False,
            'error': "Field 'status' must be one of: 'todo', 'doing', 'done'."
        }), 400
    status = status.lower()

    # 5. Validate 'priority'
    priority = payload.get('priority', 'medium')
    if not isinstance(priority, str) or priority.lower() not in ['low', 'medium', 'high']:
        return jsonify({
            'success': False,
            'error': "Field 'priority' must be one of: 'low', 'medium', 'high'."
        }), 400
    priority = priority.lower()

    # 6. Validate 'due_date'
    due_date_raw = payload.get('due_date')
    due_date, date_err = parse_due_date(due_date_raw)
    if date_err:
        return jsonify({'success': False, 'error': date_err}), 400

    # 7. Validate 'assigned_to'
    assigned_to = payload.get('assigned_to')
    if assigned_to is not None:
        if not isinstance(assigned_to, int):
            return jsonify({
                'success': False,
                'error': "Field 'assigned_to' must be an integer User ID or null."
            }), 400
        if not User.query.get(assigned_to):
            return jsonify({
                'success': False,
                'error': f"User with assigned_to ID {assigned_to} does not exist."
            }), 400

    # 8. Validate 'important'
    important = bool(payload.get('important', False))

    # 9. Determine 'created_by'
    acting_user_id = get_acting_user_id(payload)
    if not acting_user_id:
        return jsonify({
            'success': False,
            'error': "No valid user found to attribute as 'created_by'. Please create a user first."
        }), 400

    try:
        # 10. Instantiate and persist new Task
        task = Task(
            title=title,
            description=description,
            status=status,
            priority=priority,
            important=important,
            due_date=due_date,
            assigned_to=assigned_to,
            created_by=acting_user_id
        )
        db.session.add(task)
        db.session.commit()

        # 11. Record ActivityLog & TaskChange
        user_record = User.query.get(acting_user_id)
        user_label = user_record.name if user_record else f"User #{acting_user_id}"
        log_api_activity(
            action=f"API: {user_label} created task '{task.title}'",
            task_id=task.id,
            user_id=acting_user_id
        )
        record_task_change(
            task=task,
            action='added',
            user_name=user_label,
            user_id=acting_user_id,
            details='added this'
        )

        return jsonify({
            'success': True,
            'message': 'Task created successfully.',
            'task': task.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Database error creating task: {str(e)}'
        }), 500


# -------------------------------------------------------------------
# 2. READ Tasks (GET /api/tasks and GET /api/tasks/<id>)
# -------------------------------------------------------------------

@api_bp.route('/tasks', methods=['GET'])
def api_get_tasks():
    """
    List Tasks:
    Retrieves all tasks matching optional query parameter filters.

    Query Parameters:
        - status (str): Filter by 'todo', 'doing', or 'done'.
        - priority (str): Filter by 'low', 'medium', or 'high'.
        - assigned_to (int): Filter by assignee User ID.
        - created_by (int): Filter by creator User ID.
        - q (str): Search keyword matching title or description.

    Returns:
        JSON response with list of matching tasks and total count.
    """
    query = Task.query

    # Status filter
    status_filter = request.args.get('status')
    if status_filter:
        if status_filter.lower() not in ['todo', 'doing', 'done']:
            return jsonify({
                'success': False,
                'error': "Filter 'status' must be one of: 'todo', 'doing', 'done'."
            }), 400
        query = query.filter(Task.status == status_filter.lower())

    # Priority filter
    priority_filter = request.args.get('priority')
    if priority_filter:
        if priority_filter.lower() not in ['low', 'medium', 'high']:
            return jsonify({
                'success': False,
                'error': "Filter 'priority' must be one of: 'low', 'medium', 'high'."
            }), 400
        query = query.filter(Task.priority == priority_filter.lower())

    # Assignee filter
    assigned_to_filter = request.args.get('assigned_to', type=int)
    if assigned_to_filter:
        query = query.filter(Task.assigned_to == assigned_to_filter)

    # Creator filter
    created_by_filter = request.args.get('created_by', type=int)
    if created_by_filter:
        query = query.filter(Task.created_by == created_by_filter)

    # Keyword search
    search_keyword = request.args.get('q', type=str, default='').strip()
    if search_keyword:
        query = query.filter(
            (Task.title.ilike(f"%{search_keyword}%")) |
            (Task.description.ilike(f"%{search_keyword}%"))
        )

    tasks = query.order_by(Task.created_at.desc()).all()

    # Log retrieval action in ActivityLog
    acting_user_id = get_acting_user_id()
    log_api_activity(
        action=f"API: Retrieved list of {len(tasks)} tasks",
        task_id=None,
        user_id=acting_user_id
    )

    return jsonify({
        'success': True,
        'count': len(tasks),
        'tasks': [t.to_dict() for t in tasks]
    }), 200


@api_bp.route('/tasks/<int:task_id>', methods=['GET'])
def api_get_task(task_id: int):
    """
    Get Single Task:
    Fetches the detailed record of a task by its primary key ID.

    Returns:
        JSON response with the task object or 404 if not found.
    """
    task = Task.query.get(task_id)
    if not task:
        return jsonify({
            'success': False,
            'error': f"Task with ID {task_id} not found."
        }), 404

    # Log retrieval
    acting_user_id = get_acting_user_id()
    log_api_activity(
        action=f"API: Retrieved details for task '{task.title}'",
        task_id=task.id,
        user_id=acting_user_id
    )

    return jsonify({
        'success': True,
        'task': task.to_dict()
    }), 200


# -------------------------------------------------------------------
# 3. UPDATE Task (PUT /api/tasks/<id> and PATCH /api/tasks/<id>)
# -------------------------------------------------------------------

@api_bp.route('/tasks/<int:task_id>', methods=['PUT', 'PATCH'])
def api_update_task(task_id: int):
    """
    Update Task:
    Accepts full or partial updates for an existing task.

    Modifiable fields:
        - title (str)
        - description (str or null)
        - status (str: 'todo', 'doing', 'done')
        - priority (str: 'low', 'medium', 'high')
        - due_date (str: 'YYYY-MM-DD' or null)
        - assigned_to (int: User ID or null)

    Returns:
        JSON response with updated task or 400/404 error.
    """
    task = Task.query.get(task_id)
    if not task:
        return jsonify({
            'success': False,
            'error': f"Task with ID {task_id} not found."
        }), 404

    if not request.is_json:
        return jsonify({
            'success': False,
            'error': 'Request Content-Type must be application/json.'
        }), 400

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({
            'success': False,
            'error': 'Malformed JSON body.'
        }), 400

    changes = []

    # Update Title
    if 'title' in payload:
        new_title = payload['title']
        if not new_title or not isinstance(new_title, str) or not new_title.strip():
            return jsonify({
                'success': False,
                'error': "Field 'title' cannot be empty."
            }), 400
        new_title = new_title.strip()
        if len(new_title) > 200:
            return jsonify({
                'success': False,
                'error': "Field 'title' cannot exceed 200 characters."
            }), 400
        if task.title != new_title:
            changes.append(f"title changed to '{new_title}'")
            task.title = new_title

    # Update Description
    if 'description' in payload:
        new_desc = payload['description']
        if new_desc is not None and not isinstance(new_desc, str):
            return jsonify({
                'success': False,
                'error': "Field 'description' must be a string or null."
            }), 400
        clean_desc = new_desc.strip() if new_desc else None
        if task.description != clean_desc:
            changes.append("description updated")
            task.description = clean_desc

    # Update Status
    if 'status' in payload:
        new_status = payload['status']
        if not isinstance(new_status, str) or new_status.lower() not in ['todo', 'doing', 'done']:
            return jsonify({
                'success': False,
                'error': "Field 'status' must be one of: 'todo', 'doing', 'done'."
            }), 400
        new_status = new_status.lower()
        if task.status != new_status:
            changes.append(f"status changed from '{task.status}' to '{new_status}'")
            task.status = new_status

    # Update Priority
    if 'priority' in payload:
        new_priority = payload['priority']
        if not isinstance(new_priority, str) or new_priority.lower() not in ['low', 'medium', 'high']:
            return jsonify({
                'success': False,
                'error': "Field 'priority' must be one of: 'low', 'medium', 'high'."
            }), 400
        new_priority = new_priority.lower()
        if task.priority != new_priority:
            changes.append(f"priority changed to '{new_priority}'")
            task.priority = new_priority

    # Update Due Date
    if 'due_date' in payload:
        due_date_raw = payload['due_date']
        new_due_date, date_err = parse_due_date(due_date_raw)
        if date_err:
            return jsonify({'success': False, 'error': date_err}), 400
        if task.due_date != new_due_date:
            changes.append(f"due_date updated to {new_due_date.isoformat() if new_due_date else 'None'}")
            task.due_date = new_due_date

    # Update Assignee
    if 'assigned_to' in payload:
        new_assignee_id = payload['assigned_to']
        if new_assignee_id is not None:
            if not isinstance(new_assignee_id, int):
                return jsonify({
                    'success': False,
                    'error': "Field 'assigned_to' must be an integer User ID or null."
                }), 400
            assignee_user = User.query.get(new_assignee_id)
            if not assignee_user:
                return jsonify({
                    'success': False,
                    'error': f"User with assigned_to ID {new_assignee_id} does not exist."
                }), 400
            if task.assigned_to != new_assignee_id:
                changes.append(f"assigned to '{assignee_user.name}'")
                task.assigned_to = new_assignee_id
        else:
            if task.assigned_to is not None:
                changes.append("unassigned")
                task.assigned_to = None

    # Update Important boolean (Eisenhower Matrix)
    if 'important' in payload:
        new_important = bool(payload['important'])
        if task.important != new_important:
            changes.append(f"marked as {'important' if new_important else 'not important'}")
            task.important = new_important

    # Update Urgent status (Due within 48 hours)
    from datetime import date, timedelta
    today = date.today()

    if 'urgent' in payload:
        target_urgent = bool(payload['urgent'])
        if target_urgent:
            # Treat due within 48 hours as urgent: if due_date is None or > 2 days away or in the past
            if not task.due_date or (task.due_date - today).days > 2 or task.due_date < today:
                task.due_date = today + timedelta(days=1)
                changes.append("set due date within 48 hours (urgent)")
        else:
            # Not urgent: push deadline beyond 48 hours (e.g. 7 days from now)
            if task.due_date and (task.due_date - today).days <= 2:
                task.due_date = today + timedelta(days=7)
                changes.append("extended deadline beyond 48 hours (not urgent)")

    # Update Eisenhower Matrix Quadrant (Q1, Q2, Q3, Q4)
    if 'quadrant' in payload:
        target_q = str(payload['quadrant']).lower().strip()
        if target_q == 'q1':  # Urgent & Important (Do First)
            task.important = True
            if not task.due_date or (task.due_date - today).days > 2 or task.due_date < today:
                task.due_date = today + timedelta(days=1)
            changes.append("moved to Quadrant 1 (Urgent & Important: Do First)")
        elif target_q == 'q2':  # Not Urgent & Important (Schedule)
            task.important = True
            if task.due_date and (task.due_date - today).days <= 2:
                task.due_date = today + timedelta(days=7)
            changes.append("moved to Quadrant 2 (Not Urgent & Important: Schedule)")
        elif target_q == 'q3':  # Urgent & Not Important (Delegate)
            task.important = False
            if not task.due_date or (task.due_date - today).days > 2 or task.due_date < today:
                task.due_date = today + timedelta(days=1)
            changes.append("moved to Quadrant 3 (Urgent & Not Important: Delegate)")
        elif target_q == 'q4':  # Not Urgent & Not Important (Eliminate)
            task.important = False
            if task.due_date and (task.due_date - today).days <= 2:
                task.due_date = today + timedelta(days=7)
            changes.append("moved to Quadrant 4 (Not Urgent & Not Important: Eliminate)")

    try:
        db.session.commit()

        # Log changes to ActivityLog
        acting_user_id = get_acting_user_id(payload)
        user_record = User.query.get(acting_user_id) if acting_user_id else None
        user_label = user_record.name if user_record else "API Client"

        change_desc = ", ".join(changes) if changes else "no fields modified"
        log_api_activity(
            action=f"API: {user_label} updated task '{task.title}': {change_desc}",
            task_id=task.id,
            user_id=acting_user_id
        )

        action_type = 'moved' if ('status' in payload or 'quadrant' in payload) else 'edited'
        if 'status' in payload:
            action_details = f"moved this to {task.status.capitalize()}"
        elif 'quadrant' in payload:
            action_details = f"moved this to {payload.get('quadrant', '').upper()}"
        else:
            action_details = "edited this"

        record_task_change(
            task=task,
            action=action_type,
            user_name=user_label,
            user_id=acting_user_id,
            details=action_details
        )

        return jsonify({
            'success': True,
            'message': 'Task updated successfully.',
            'changes': changes,
            'task': task.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Database error updating task: {str(e)}'
        }), 500


# -------------------------------------------------------------------
# 4. DELETE Task (DELETE /api/tasks/<id>)
# -------------------------------------------------------------------

@api_bp.route('/tasks/<int:task_id>', methods=['DELETE'])
def api_delete_task(task_id: int):
    """
    Delete Task:
    Permanently deletes a task by ID and creates an ActivityLog audit record.

    Returns:
        JSON response with success confirmation or 404 error.
    """
    task = Task.query.get(task_id)
    if not task:
        return jsonify({
            'success': False,
            'error': f"Task with ID {task_id} not found."
        }), 404

    task_title = task.title
    acting_user_id = get_acting_user_id()
    user_record = User.query.get(acting_user_id) if acting_user_id else None
    user_label = user_record.name if user_record else "API Client"

    try:
        # Nullify task_id in previous activity logs so audit records are permanently retained
        ActivityLog.query.filter_by(task_id=task.id).update({'task_id': None})

        # Delete task
        db.session.delete(task)
        db.session.commit()

        # Log deletion in ActivityLog & TaskChange
        log_api_activity(
            action=f"API: {user_label} deleted task '{task_title}' (ID {task_id})",
            task_id=None,
            user_id=acting_user_id
        )
        record_task_change(
            task=task,
            action='deleted',
            user_name=user_label,
            user_id=acting_user_id,
            details='deleted this'
        )

        return jsonify({
            'success': True,
            'message': f"Task '{task_title}' (ID {task_id}) deleted successfully."
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Database error deleting task: {str(e)}'
        }), 500


# -------------------------------------------------------------------
# 5. Activity Log API (GET /api/activity)
# -------------------------------------------------------------------

@api_bp.route('/activity', methods=['GET'])
def api_get_activity():
    """
    Retrieve Activity Logs:
    Returns chronological audit trail records with optional pagination/limit.

    Query Parameters:
        - limit (int): Max records to return (default: 50, max: 200).
        - task_id (int): Filter by specific task ID.
        - user_id (int): Filter by specific user ID.

    Returns:
        JSON list of serialized activity log entries.
    """
    limit = min(request.args.get('limit', default=50, type=int), 200)
    query = ActivityLog.query

    task_id_filter = request.args.get('task_id', type=int)
    if task_id_filter:
        query = query.filter(ActivityLog.task_id == task_id_filter)

    user_id_filter = request.args.get('user_id', type=int)
    if user_id_filter:
        query = query.filter(ActivityLog.user_id == user_id_filter)

    logs = query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()

    return jsonify({
        'success': True,
        'count': len(logs),
        'activity': [log.to_dict() for log in logs]
    }), 200


# -------------------------------------------------------------------
# 6. Analytics & Statistics API (GET /api/analytics, GET /api/stats)
# -------------------------------------------------------------------

@api_bp.route('/analytics', methods=['GET'])
@api_bp.route('/stats', methods=['GET'])
def api_get_analytics():
    """
    Retrieve aggregated dashboard analytics for Chart.js visualization:
    - Status distribution (To Do, Doing, Done) for Doughnut chart.
    - Member distribution (tasks per registered user + Unassigned) for Bar chart.
    - Priority distribution (High, Medium, Low).
    - Summary metrics: total tasks, completion rate, overdue, and due-soon.
    """
    all_tasks = Task.query.all()
    all_users = User.query.order_by(User.name.asc()).all()

    total_tasks = len(all_tasks)
    todo_tasks = sum(1 for t in all_tasks if t.status == 'todo')
    doing_tasks = sum(1 for t in all_tasks if t.status == 'doing')
    done_tasks = sum(1 for t in all_tasks if t.status == 'done')

    overdue_tasks = sum(1 for t in all_tasks if t.is_overdue)
    due_soon_tasks = sum(1 for t in all_tasks if t.is_due_soon)
    completion_rate = round((done_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0

    # Tasks per status (Doughnut chart)
    status_distribution = {
        'labels': ['To Do', 'Doing', 'Done'],
        'counts': [todo_tasks, doing_tasks, done_tasks],
        'colors': ['#3b82f6', '#8b5cf6', '#10b981']
    }

    # Tasks per member and comprehensive Workload Analysis
    workload_summary = calculate_workload_summary(all_tasks, all_users)
    member_labels = [m['name'] for m in workload_summary['members']]
    member_counts = [m['total'] for m in workload_summary['members']]
    member_details = workload_summary['members']

    # Priority breakdown
    high_prio = sum(1 for t in all_tasks if t.priority == 'high')
    medium_prio = sum(1 for t in all_tasks if t.priority == 'medium')
    low_prio = sum(1 for t in all_tasks if t.priority == 'low')

    priority_distribution = {
        'labels': ['High', 'Medium', 'Low'],
        'counts': [high_prio, medium_prio, low_prio],
        'colors': ['#ef4444', '#f59e0b', '#10b981']
    }

    # Daily Focus Time computation for the last 7 days
    today = date.today()
    focus_labels = []
    focus_minutes = []
    focus_hours = []

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_label = 'Today' if i == 0 else day.strftime('%a, %b %d')
        focus_labels.append(day_label)

        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())

        day_minutes = db.session.query(
            db.func.coalesce(db.func.sum(TimeLog.duration_minutes), 0)
        ).filter(
            TimeLog.created_at >= day_start,
            TimeLog.created_at <= day_end
        ).scalar() or 0

        focus_minutes.append(int(day_minutes))
        focus_hours.append(round(day_minutes / 60.0, 1))

    total_focus_minutes = db.session.query(
        db.func.coalesce(db.func.sum(TimeLog.duration_minutes), 0)
    ).scalar() or 0

    hours = total_focus_minutes // 60
    mins = total_focus_minutes % 60
    formatted_total_focus = f"{hours}h {mins}m" if hours > 0 and mins > 0 else (f"{hours}h" if hours > 0 else f"{mins}m")

    daily_focus_time = {
        'labels': focus_labels,
        'minutes': focus_minutes,
        'hours': focus_hours,
        'total_minutes': int(total_focus_minutes),
        'formatted_total': formatted_total_focus
    }

    return jsonify({
        'success': True,
        'summary': {
            'total': total_tasks,
            'todo': todo_tasks,
            'doing': doing_tasks,
            'done': done_tasks,
            'overdue': overdue_tasks,
            'due_soon': due_soon_tasks,
            'completion_rate': completion_rate,
            'total_focus_minutes': int(total_focus_minutes),
            'formatted_total_focus': formatted_total_focus
        },
        'status_distribution': status_distribution,
        'member_distribution': {
            'labels': member_labels,
            'counts': member_counts,
            'members': member_details
        },
        'priority_distribution': priority_distribution,
        'daily_focus_time': daily_focus_time,
        'workload_summary': workload_summary
    }), 200


# -------------------------------------------------------------------
# 8. Natural Language Quick-Add Parser Endpoint (POST / GET /api/tasks/parse)
# -------------------------------------------------------------------

@api_bp.route('/tasks/parse', methods=['GET', 'POST'])
def api_parse_task():
    """
    Parses a natural language task description string using Python regex
    and the dateparser library.

    Accepts:
        POST body: JSON {'text': 'Finish report tomorrow high priority @ravi important'}
        GET query: ?text=... or ?q=...

    Returns:
        JSON with parsed attributes (title, due_date, due_date_human, priority,
        important, assignee_id, assignee_name, assignee_found, etc.)
    """
    from app.task_parser import parse_quick_task

    text = ''
    if request.method == 'POST' and request.is_json:
        payload = request.get_json(silent=True) or {}
        text = payload.get('text', '')
    elif request.method == 'GET':
        text = request.args.get('text') or request.args.get('q', '')
    else:
        text = request.form.get('text', '')

    text = str(text or '').strip()
    if not text:
        return jsonify({
            'success': True,
            'parsed': None,
            'message': 'Empty input text'
        }), 200

    # Retrieve all registered users for mention resolution
    all_users = [{'id': u.id, 'name': u.name, 'email': u.email} for u in User.query.all()]
    parsed = parse_quick_task(text, users=all_users)

    return jsonify({
        'success': True,
        'parsed': parsed
    }), 200


# -------------------------------------------------------------------
# 9. Natural Language Quick-Create Endpoint (POST /api/tasks/quick-add)
# -------------------------------------------------------------------

@api_bp.route('/tasks/quick-add', methods=['POST'])
def api_quick_add_task():
    """
    Creates a new task directly from a natural language sentence.
    Uses app.task_parser to extract title, due date, priority, assignee,
    and importance, then persists the record and logs the activity.
    """
    from app.task_parser import parse_quick_task
    from datetime import datetime

    raw_text = ''
    overrides = {}
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        raw_text = payload.get('text', '')
        overrides = payload
    else:
        raw_text = request.form.get('quick_text', '') or request.form.get('text', '')

    raw_text = str(raw_text or '').strip()
    if not raw_text:
        return jsonify({
            'success': False,
            'error': 'Text is required to create a task.'
        }), 400

    all_users = [{'id': u.id, 'name': u.name, 'email': u.email} for u in User.query.all()]
    parsed = parse_quick_task(raw_text, users=all_users)

    if not parsed or not parsed.get('title'):
        return jsonify({
            'success': False,
            'error': 'Could not extract a valid task title from input.'
        }), 400

    # Allow explicit overrides from payload if provided
    title = overrides.get('title') or parsed['title']
    priority = overrides.get('priority') or parsed['priority']
    important = overrides.get('important') if 'important' in overrides else parsed['important']
    assigned_to = overrides.get('assigned_to') if 'assigned_to' in overrides else parsed['assignee_id']
    due_date_str = overrides.get('due_date') or parsed['due_date']
    status = overrides.get('status', 'todo')

    # Parse due_date date object
    due_date_obj = None
    if due_date_str:
        try:
            due_date_obj = datetime.strptime(str(due_date_str).strip()[:10], '%Y-%m-%d').date()
        except ValueError:
            due_date_obj = None

    acting_user_id = get_acting_user_id(overrides if request.is_json else None)
    if not acting_user_id:
        return jsonify({
            'success': False,
            'error': 'No registered user found to attribute task creation to.'
        }), 400

    try:
        new_task = Task(
            title=title,
            description=None,
            status=status,
            priority=priority,
            important=important,
            due_date=due_date_obj,
            assigned_to=assigned_to,
            created_by=acting_user_id
        )
        db.session.add(new_task)
        db.session.commit()

        user_record = User.query.get(acting_user_id)
        user_name = user_record.name if user_record else f"User #{acting_user_id}"
        log_api_activity(
            action=f"Quick-Add: {user_name} created '{new_task.title}' via quick-add bar",
            task_id=new_task.id,
            user_id=acting_user_id
        )
        record_task_change(
            task=new_task,
            action='added',
            user_name=user_name,
            user_id=acting_user_id,
            details='added this'
        )

        return jsonify({
            'success': True,
            'message': f"Task '{new_task.title}' created successfully!",
            'task': new_task.to_dict(),
            'parsed': parsed
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Failed to create task: {str(e)}'
        }), 500


# -------------------------------------------------------------------
# 10. Task Focus Time Log Endpoints (POST /api/tasks/<id>/timelog)
# -------------------------------------------------------------------

@api_bp.route('/tasks/<int:task_id>/timelog', methods=['POST'])
def api_log_task_time(task_id: int):
    """
    Records a focus time session for a specific task.

    Accepts:
        JSON body: {'duration_minutes': 25} (default: 25)

    Returns:
        JSON response with updated total focus time and the created timelog record.
    """
    task = Task.query.get(task_id)
    if not task:
        return jsonify({
            'success': False,
            'error': f'Task with ID {task_id} not found.'
        }), 404

    payload = request.get_json(silent=True) or {}
    duration = payload.get('duration_minutes', 25)
    try:
        duration = int(duration)
        if duration <= 0:
            duration = 25
    except (ValueError, TypeError):
        duration = 25

    acting_user_id = get_acting_user_id(payload)
    if not acting_user_id:
        acting_user_id = task.assigned_to or task.created_by

    try:
        timelog = TimeLog(
            task_id=task.id,
            user_id=acting_user_id,
            duration_minutes=duration
        )
        db.session.add(timelog)
        db.session.commit()

        user_record = User.query.get(acting_user_id)
        user_name = user_record.name if user_record else f"User #{acting_user_id}"
        log_api_activity(
            action=f"Focus: {user_name} completed a {duration}-minute focus session on '{task.title}'",
            task_id=task.id,
            user_id=acting_user_id
        )

        return jsonify({
            'success': True,
            'message': f"{duration} minutes logged on '{task.title}'!",
            'task_id': task.id,
            'total_focus_minutes': task.total_focus_minutes,
            'formatted_focus_time': task.formatted_focus_time,
            'timelog': timelog.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Failed to record focus time: {str(e)}'
        }), 500


@api_bp.route('/tasks/<int:task_id>/timelog', methods=['GET'])
def api_get_task_timelogs(task_id: int):
    """
    Retrieves all focus time logs recorded for a task.
    """
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': f'Task with ID {task_id} not found.'}), 404

    logs = task.time_logs.order_by(TimeLog.created_at.desc()).all()
    return jsonify({
        'success': True,
        'task_id': task.id,
        'total_focus_minutes': task.total_focus_minutes,
        'formatted_focus_time': task.formatted_focus_time,
        'count': len(logs),
        'timelogs': [log.to_dict() for log in logs]
    }), 200


# -------------------------------------------------------------------
# 11. Lightweight Live Changes Polling (GET /api/changes?since=<timestamp>)
# -------------------------------------------------------------------

@api_bp.route('/changes', methods=['GET'])
def api_get_changes():
    """
    Lightweight polling endpoint polled every 3 seconds from main.js.
    Returns all task mutations (moves, edits, adds, deletes) that occurred
    after the given 'since' timestamp, allowing real-time multi-user live sync.

    Query Params:
        since (str): ISO 8601 string (e.g. '2026-11-05T13:30:00Z') or Unix epoch float.

    Returns:
        JSON with change records, server timestamp, and count.
    """
    since_str = request.args.get('since', '').strip()
    since_dt = None

    if since_str:
        try:
            # Check if numeric epoch timestamp
            if since_str.replace('.', '', 1).isdigit():
                since_dt = datetime.utcfromtimestamp(float(since_str))
            else:
                # ISO timestamp string
                clean_ts = since_str.replace('Z', '').split('+')[0]
                since_dt = datetime.fromisoformat(clean_ts)
        except Exception:
            since_dt = datetime.utcnow() - timedelta(seconds=15)
    else:
        since_dt = datetime.utcnow() - timedelta(seconds=15)

    # Query changes since timestamp
    changes = TaskChange.query.filter(
        TaskChange.timestamp > since_dt
    ).order_by(TaskChange.timestamp.asc()).limit(50).all()

    server_now = datetime.utcnow()
    return jsonify({
        'success': True,
        'server_time': server_now.isoformat() + 'Z',
        'since': since_dt.isoformat() + 'Z',
        'count': len(changes),
        'changes': [c.to_dict() for c in changes]
    }), 200


# -------------------------------------------------------------------
# 11. "Next Up" Top 5 Priority Tasks API (GET /api/tasks/next-up)
# -------------------------------------------------------------------

@api_bp.route('/tasks/next-up', methods=['GET'])
def api_get_next_up():
    """
    Returns the top 5 highest-scoring non-done tasks for the currently authenticated user
    (or filtered by ?user_id=<id>).
    
    Uses the priority scoring formula:
    priority weight + importance weight + days until due + overdue bonus.
    """
    target_user_id = request.args.get('user_id', type=int)
    if not target_user_id and current_user and current_user.is_authenticated:
        target_user_id = current_user.id

    all_tasks = Task.query.all()

    if target_user_id:
        # Prioritize non-done tasks directly assigned to this user
        user_tasks = [t for t in all_tasks if t.assigned_to == target_user_id and t.status != 'done']
        user_tasks.sort(key=lambda t: t.score, reverse=True)
        top_tasks = user_tasks[:5]

        # Supplement with high-scoring active tasks if fewer than 5
        if len(top_tasks) < 5:
            supplements = [t for t in all_tasks if t.status != 'done' and t not in top_tasks]
            supplements.sort(key=lambda t: t.score, reverse=True)
            top_tasks.extend(supplements[:(5 - len(top_tasks))])
    else:
        top_tasks = [t for t in all_tasks if t.status != 'done']
        top_tasks.sort(key=lambda t: t.score, reverse=True)
        top_tasks = top_tasks[:5]

    user_name = "You"
    if target_user_id:
        target_user = User.query.get(target_user_id)
        if target_user:
            user_name = target_user.name

    return jsonify({
        'success': True,
        'user_id': target_user_id,
        'user_name': user_name,
        'count': len(top_tasks),
        'tasks': [t.to_dict() for t in top_tasks]
    }), 200




