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

from datetime import datetime, date
from flask import Blueprint, request, jsonify
from flask_login import current_user
from app import db
from app.models import Task, User, ActivityLog

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

        # 11. Record ActivityLog
        user_record = User.query.get(acting_user_id)
        user_label = user_record.name if user_record else f"User #{acting_user_id}"
        log_api_activity(
            action=f"API: {user_label} created task '{task.title}'",
            task_id=task.id,
            user_id=acting_user_id
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

        # Log deletion in ActivityLog
        log_api_activity(
            action=f"API: {user_label} deleted task '{task_title}' (ID {task_id})",
            task_id=None,
            user_id=acting_user_id
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

    # Tasks per member (Bar chart)
    member_labels = []
    member_counts = []
    member_details = []

    for user in all_users:
        user_tasks = [t for t in all_tasks if t.assigned_to == user.id]
        member_labels.append(user.name)
        member_counts.append(len(user_tasks))
        member_details.append({
            'user_id': user.id,
            'name': user.name,
            'email': user.email,
            'total': len(user_tasks),
            'todo': sum(1 for t in user_tasks if t.status == 'todo'),
            'doing': sum(1 for t in user_tasks if t.status == 'doing'),
            'done': sum(1 for t in user_tasks if t.status == 'done')
        })

    # Include unassigned tasks in member distribution
    unassigned_tasks = [t for t in all_tasks if t.assigned_to is None]
    if unassigned_tasks or len(all_users) == 0:
        member_labels.append('Unassigned')
        member_counts.append(len(unassigned_tasks))
        member_details.append({
            'user_id': None,
            'name': 'Unassigned',
            'email': '',
            'total': len(unassigned_tasks),
            'todo': sum(1 for t in unassigned_tasks if t.status == 'todo'),
            'doing': sum(1 for t in unassigned_tasks if t.status == 'doing'),
            'done': sum(1 for t in unassigned_tasks if t.status == 'done')
        })

    # Priority breakdown
    high_prio = sum(1 for t in all_tasks if t.priority == 'high')
    medium_prio = sum(1 for t in all_tasks if t.priority == 'medium')
    low_prio = sum(1 for t in all_tasks if t.priority == 'low')

    priority_distribution = {
        'labels': ['High', 'Medium', 'Low'],
        'counts': [high_prio, medium_prio, low_prio],
        'colors': ['#ef4444', '#f59e0b', '#10b981']
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
            'completion_rate': completion_rate
        },
        'status_distribution': status_distribution,
        'member_distribution': {
            'labels': member_labels,
            'counts': member_counts,
            'members': member_details
        },
        'priority_distribution': priority_distribution
    }), 200
