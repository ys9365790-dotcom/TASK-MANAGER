/**
 * static/js/main.js
 * -----------------
 * Client-side JavaScript enhancements for the TaskManager Flask application.
 * 
 * Features:
 * 1. Three-Column Kanban Board with SortableJS Drag-and-Drop:
 *    - Columns: To Do ('todo'), Doing ('doing'), Done ('done').
 *    - Moving a card across columns immediately sends a PATCH request via fetch()
 *      to `/api/tasks/<id>` to persist the new status in SQLite.
 *    - Updates column counter badges dynamically with rollback on failure.
 *    - Displays non-intrusive floating toast notifications for user feedback.
 * 2. Visual Urgency and Priority Badges:
 *    - Red border, red accent, background tint, and badge for Overdue tasks.
 *    - Amber border, amber accent, background tint, and badge for tasks Due within 24 Hours.
 *    - Color-coded badges for High (red), Medium (amber), and Low (green) priority.
 *    - Real-time resolution/re-application of urgency styling when status changes.
 * 3. Client-Side Instant Filtering (No Page Reload):
 *    - Search box matching title, description, and assignee name.
 *    - Priority filter (All, High, Medium, Low).
 *    - Assignee filter (All, Unassigned, or any specific registered user).
 *    - Live result counters and instant filter reset without page reload.
 * 4. Inline Task Assignment:
 *    - Assign any task to any registered user directly on the card.
 *    - Asynchronously persists changes via fetch() and updates active client filters.
 * 5. Auto-dismissing flash notifications with smooth fade-out.
 */

document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();
    initQuickAddBar();
    initFocusTimer();
    initLiveBoardSync();
    initSortableKanban();
    initSortableMatrix();
    initViewModeToggle();
    initFlashAutoDismiss();
    initClientFilter();
    initQuickAssignee();
    initAsyncStatusTransitions();
    initMetricCountUp();
    initPasswordToggle();
    initAuthFormLoading();
    initDeleteTaskModal();
    initNavbarToggle();
});

/**
 * Initializes SortableJS drag-and-drop across the three Kanban columns:
 * To Do ('todo'), Doing ('doing'), and Done ('done').
 */
function initSortableKanban() {
    const sortableLists = document.querySelectorAll('#kanban-board-view .sortable-list');
    if (!sortableLists.length) return;

    if (typeof Sortable === 'undefined') {
        console.warn('SortableJS library not loaded. Drag and drop is disabled.');
        return;
    }

    sortableLists.forEach((list) => {
        new Sortable(list, {
            group: 'kanban-board',         // Shared group enables dragging between all 3 columns
            animation: 250,                // Smooth 250ms transition animation
            draggable: '.task-card',       // Only task cards are draggable; empty-state placeholders remain intact
            ghostClass: 'sortable-ghost',  // Class applied to drop placeholder
            chosenClass: 'sortable-chosen',// Class applied while picking up a card
            dragClass: 'sortable-drag',    // Class applied to active dragging element
            filter: '.card-controls, .card-status-actions, .assignee-quick-select, a, button, input, textarea, select',
            preventOnFilter: false,

            // Triggered when a card is dropped
            async onEnd(evt) {
                const item = evt.item;
                const fromColumn = evt.from;
                const toColumn = evt.to;

                // If dropped within the exact same column, no status update needed
                if (fromColumn === toColumn) {
                    return;
                }

                const taskId = item.dataset.taskId;
                const newStatus = toColumn.dataset.status;
                const oldStatus = fromColumn.dataset.status;
                const taskTitle = item.querySelector('.task-title')?.textContent?.trim() || 'Task';

                if (!taskId || !newStatus) return;

                // Optimistically update column badge counts and empty-state placeholders
                updateColumnMetrics();

                try {
                    // Send asynchronous PATCH request to REST API
                    const response = await fetch(`/api/tasks/${taskId}`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        },
                        body: JSON.stringify({ status: newStatus })
                    });

                    const data = await response.json();

                    if (!response.ok || !data.success) {
                        throw new Error(data.error || 'Failed to update task status.');
                    }

                    // Update data-status on the card
                    item.dataset.status = newStatus;

                    // Update quick-action buttons inside the card
                    updateCardActionButtons(item, newStatus, taskId);

                    // Dynamically update card urgency (overdue in red / due <24h in amber)
                    if (data.task) {
                        updateCardUrgency(item, data.task);
                    }

                    // Re-calculate column metrics & urgency counters
                    updateColumnMetrics();
                    applyClientFilters();

                    // Show success toast notification
                    showToast(`Moved "${taskTitle}" to ${formatStatusName(newStatus)}`, 'success');

                } catch (err) {
                    console.error('Status update failed, reverting position:', err);

                    // Revert the card back to its original column
                    const originalNextSibling = fromColumn.children[evt.oldIndex] || null;
                    fromColumn.insertBefore(item, originalNextSibling);

                    // Revert column counts
                    updateColumnMetrics();
                    applyClientFilters();

                    // Display error toast
                    showToast(`Failed to update status: ${err.message}`, 'error');
                }
            }
        });
    });

    // Initial check for empty states & counters
    updateColumnMetrics();
}

/**
 * Dynamically updates the card's visual urgency highlights:
 * - Red border, red accent, red tinted background, and red ⏰ Overdue badge if overdue.
 * - Amber border, amber accent, amber tinted background, and amber ⏳ Due <24h badge if due within 24h.
 * - Resolves / removes highlights when task is completed ('done') or not urgent.
 */
function updateCardUrgency(card, task) {
    if (!card || !task) return;

    const badgesContainer = card.querySelector('.card-badges');
    const existingUrgencyBadge = card.querySelector('.badge-urgency');
    const metaDue = card.querySelector('.meta-due');

    // Remove existing urgency classes and badges
    card.classList.remove('task-overdue', 'task-due-soon');
    if (existingUrgencyBadge) {
        existingUrgencyBadge.remove();
    }
    if (metaDue) {
        metaDue.classList.remove('meta-overdue', 'meta-due-soon', 'text-danger', 'text-warning');
    }

    // Update dataset on card
    card.dataset.isOverdue = task.is_overdue ? 'true' : 'false';
    card.dataset.isDueSoon = task.is_due_soon ? 'true' : 'false';
    card.dataset.isUrgent = task.is_urgent ? 'true' : 'false';
    if (task.eisenhower_quadrant) {
        card.dataset.quadrant = task.eisenhower_quadrant;
    }
    if (typeof task.important !== 'undefined') {
        card.dataset.important = task.important ? 'true' : 'false';
    }

    // Only apply overdue / due-soon highlights if the task is not yet 'done'
    if (task.status !== 'done') {
        if (task.is_overdue) {
            card.classList.add('task-overdue');
            if (badgesContainer) {
                const overdueBadge = document.createElement('span');
                overdueBadge.className = 'badge badge-urgency badge-overdue';
                overdueBadge.title = 'Past due date!';
                overdueBadge.innerHTML = '⏰ Overdue';
                badgesContainer.appendChild(overdueBadge);
            }
            if (metaDue) {
                metaDue.classList.add('meta-overdue', 'text-danger');
            }
        } else if (task.is_due_soon) {
            card.classList.add('task-due-soon');
            if (badgesContainer) {
                const dueSoonBadge = document.createElement('span');
                dueSoonBadge.className = 'badge badge-urgency badge-due-soon';
                dueSoonBadge.title = 'Due within 48 hours!';
                dueSoonBadge.innerHTML = '⏳ Due &lt;48h';
                badgesContainer.appendChild(dueSoonBadge);
            }
            if (metaDue) {
                metaDue.classList.add('meta-due-soon', 'text-warning');
            }
        }
    }
}

/**
 * Updates column header badges and metric counter cards based on current DOM elements.
 * Also toggles visibility of the "No tasks" placeholder in empty columns and updates
 * the overdue / due-soon summary counters.
 */
function updateColumnMetrics() {
    const statuses = ['todo', 'doing', 'done'];

    statuses.forEach((status) => {
        const list = document.getElementById(`list-${status}`);
        const badge = document.getElementById(`count-${status}`);
        const metric = document.getElementById(`metric-${status}-count`);
        const emptyState = document.getElementById(`empty-${status}`);

        if (list) {
            // Count all cards inside this list (regardless of client filtering for the base metric)
            const cards = list.querySelectorAll('.task-card');
            const visibleCards = list.querySelectorAll('.task-card:not([style*="display: none"])');
            const count = visibleCards.length;

            if (badge) badge.textContent = count;
            if (metric) metric.textContent = cards.length;

            if (emptyState) {
                emptyState.style.display = count === 0 ? 'block' : 'none';
            }
        }
    });

    // Update overdue and due soon summary counters
    const overdueCards = document.querySelectorAll('.task-card.task-overdue');
    const dueSoonCards = document.querySelectorAll('.task-card.task-due-soon');
    const overdueCardEl = document.getElementById('metric-card-overdue');
    const dueSoonCardEl = document.getElementById('metric-card-due-soon');
    const overdueCountEl = document.getElementById('metric-overdue-count');
    const dueSoonCountEl = document.getElementById('metric-due-soon-count');

    if (overdueCountEl) overdueCountEl.textContent = overdueCards.length;
    if (overdueCardEl) overdueCardEl.style.display = overdueCards.length > 0 ? '' : 'none';

    if (dueSoonCountEl) dueSoonCountEl.textContent = dueSoonCards.length;
    if (dueSoonCardEl) dueSoonCardEl.style.display = dueSoonCards.length > 0 ? '' : 'none';

    // Update total count
    const totalCountEl = document.getElementById('metric-total-count');
    if (totalCountEl) {
        const allCards = document.querySelectorAll('.task-card');
        totalCountEl.textContent = allCards.length;
    }
}

/**
 * Updates the quick-move button group inside a task card after its status changes.
 * Ensures the user can still use click buttons for accessibility.
 */
function updateCardActionButtons(card, currentStatus, taskId) {
    const btnGroup = card.querySelector('.status-btn-group');
    if (!btnGroup) return;

    const availableStatuses = [
        { key: 'todo', label: 'To Do', class: 'shift-todo' },
        { key: 'doing', label: 'Doing', class: 'shift-doing' },
        { key: 'done', label: 'Done', class: 'shift-done' }
    ];

    btnGroup.innerHTML = '';

    availableStatuses.forEach((st) => {
        if (st.key !== currentStatus) {
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = `/tasks/${taskId}/status`;
            form.style.display = 'inline';

            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'status';
            input.value = st.key;

            const btn = document.createElement('button');
            btn.type = 'submit';
            btn.className = `status-shift-btn ${st.class}`;
            btn.title = `Move to ${st.label}`;
            btn.textContent = st.label;

            form.appendChild(input);
            form.appendChild(btn);
            btnGroup.appendChild(form);
        }
    });
}

/**
 * Displays an animated floating toast notification sliding in from top-right.
 * Features an SVG icon, countdown progress bar, and interactive close button.
 * 
 * @param {string} message - Notification text to display.
 * @param {'success'|'error'|'warning'|'info'} type - Type of toast styling.
 * @param {number} duration - Auto-dismiss timeout in milliseconds (default: 4000).
 */
function showToast(message, type = 'info', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    // Normalize type (e.g. 'danger' -> 'error')
    const normalizedType = type === 'danger' ? 'error' : type;

    const toast = document.createElement('div');
    toast.className = `toast toast-${normalizedType}`;
    toast.style.setProperty('--toast-duration', `${duration}ms`);

    // 1. Icon Badge with Lucide SVG
    const iconBadge = document.createElement('div');
    iconBadge.className = 'toast-icon-badge';
    if (normalizedType === 'success') {
        iconBadge.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>`;
    } else if (normalizedType === 'error') {
        iconBadge.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>`;
    } else if (normalizedType === 'warning') {
        iconBadge.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>`;
    } else {
        iconBadge.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`;
    }

    // 2. Message Content
    const content = document.createElement('div');
    content.className = 'toast-content';
    const msg = document.createElement('div');
    msg.className = 'toast-message';
    msg.textContent = message;
    content.appendChild(msg);

    // 3. Close Button
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'toast-close-btn';
    closeBtn.setAttribute('aria-label', 'Dismiss notification');
    closeBtn.innerHTML = '&times;';

    // 4. Progress bar showing time left
    const progressTrack = document.createElement('div');
    progressTrack.className = 'toast-progress-track';
    const progressBar = document.createElement('div');
    progressBar.className = 'toast-progress-bar';
    progressTrack.appendChild(progressBar);

    toast.appendChild(iconBadge);
    toast.appendChild(content);
    toast.appendChild(closeBtn);
    toast.appendChild(progressTrack);
    container.appendChild(toast);

    // Auto-removal and hover-pause logic
    let removeTimeout = null;
    let startTime = Date.now();
    let remainingTime = duration;

    function startTimer(time) {
        startTime = Date.now();
        removeTimeout = setTimeout(() => {
            dismissToast();
        }, time);
    }

    function dismissToast() {
        if (toast.classList.contains('is-leaving')) return;
        toast.classList.add('is-leaving');
        clearTimeout(removeTimeout);
        setTimeout(() => {
            toast.remove();
        }, 280);
    }

    closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dismissToast();
    });

    toast.addEventListener('mouseenter', () => {
        clearTimeout(removeTimeout);
        remainingTime -= Date.now() - startTime;
        if (remainingTime < 300) remainingTime = 300;
    });

    toast.addEventListener('mouseleave', () => {
        startTimer(remainingTime);
    });

    startTimer(duration);
}

/**
 * Formats a raw status string into a human-readable title.
 */
function formatStatusName(status) {
    if (status === 'todo') return 'To Do';
    if (status === 'doing') return 'Doing';
    if (status === 'done') return 'Done';
    return status;
}

/**
 * Auto-dismisses standard Flask flash messages after 6 seconds.
 */
function initFlashAutoDismiss() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach((alert) => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 500);
        }, 6000);
    });
}

/**
 * Client-Side Instant Filtering:
 * Provides real-time instant search and filters for Priority and Assignee without page reload.
 */
function initClientFilter() {
    const searchInput = document.getElementById('search-input');
    const searchClearBtn = document.getElementById('search-clear-btn');
    const prioritySelect = document.getElementById('filter-priority');
    const assigneeSelect = document.getElementById('filter-assignee');
    const clearBtn = document.getElementById('btn-clear-filters');

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            if (searchClearBtn) {
                searchClearBtn.style.display = searchInput.value ? 'block' : 'none';
            }
            applyClientFilters();
        });

        if (searchClearBtn) {
            searchClearBtn.addEventListener('click', () => {
                searchInput.value = '';
                searchClearBtn.style.display = 'none';
                searchInput.focus();
                applyClientFilters();
            });
        }
    }

    if (prioritySelect) {
        prioritySelect.addEventListener('change', () => applyClientFilters());
    }

    if (assigneeSelect) {
        assigneeSelect.addEventListener('change', () => applyClientFilters());
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (searchInput) searchInput.value = '';
            if (searchClearBtn) searchClearBtn.style.display = 'none';
            if (prioritySelect) prioritySelect.value = '';
            if (assigneeSelect) assigneeSelect.value = '';
            applyClientFilters();
        });
    }

    // Run once on load to ensure initial state consistency
    applyClientFilters();
}

/**
 * Applies active search, priority, and assignee filters to all cards in the board.
 * Runs strictly on the client side with zero page reload.
 */
function applyClientFilters() {
    const searchInput = document.getElementById('search-input');
    const prioritySelect = document.getElementById('filter-priority');
    const assigneeSelect = document.getElementById('filter-assignee');
    const clearBtn = document.getElementById('btn-clear-filters');
    const filterInfo = document.getElementById('filter-result-info');

    const query = searchInput ? searchInput.value.toLowerCase().trim() : '';
    const priority = prioritySelect ? prioritySelect.value.toLowerCase() : '';
    const assignee = assigneeSelect ? assigneeSelect.value : '';

    const cards = document.querySelectorAll('.task-card');
    let visibleCount = 0;

    cards.forEach((card) => {
        const title = (card.querySelector('.task-title')?.textContent || '').toLowerCase();
        const desc = (card.querySelector('.task-description')?.textContent || '').toLowerCase();
        const cardPriority = (card.dataset.priority || '').toLowerCase();
        const cardAssigneeId = card.dataset.assigneeId || '';
        const cardAssigneeName = (card.dataset.assigneeName || '').toLowerCase();

        // 1. Check Search Query (Title, Description, or Assignee Name)
        const matchesQuery = !query || 
            title.includes(query) || 
            desc.includes(query) || 
            cardAssigneeName.includes(query);

        // 2. Check Priority Filter
        const matchesPriority = !priority || cardPriority === priority;

        // 3. Check Assignee Filter ('unassigned' or specific user ID)
        let matchesAssignee = true;
        if (assignee === 'unassigned') {
            matchesAssignee = !cardAssigneeId;
        } else if (assignee) {
            matchesAssignee = cardAssigneeId === assignee;
        }

        const isVisible = matchesQuery && matchesPriority && matchesAssignee;
        card.style.display = isVisible ? '' : 'none';
        if (isVisible) visibleCount++;
    });

    // Update column counters and empty-state placeholders (Kanban)
    const statuses = ['todo', 'doing', 'done'];
    statuses.forEach((status) => {
        const list = document.getElementById(`list-${status}`);
        const badge = document.getElementById(`count-${status}`);
        const emptyState = document.getElementById(`empty-${status}`);

        if (list) {
            const visibleInCol = list.querySelectorAll('.task-card:not([style*="display: none"])');
            const totalInCol = list.querySelectorAll('.task-card');

            if (badge) badge.textContent = visibleInCol.length;

            if (emptyState) {
                if (visibleInCol.length === 0) {
                    emptyState.style.display = 'block';
                    const isFiltered = Boolean(query || priority || assignee);
                    const titleEl = emptyState.querySelector('.empty-title') || emptyState.querySelector('p');
                    const subtitleEl = emptyState.querySelector('.empty-subtitle');
                    if (titleEl) {
                        if (isFiltered && totalInCol.length > 0) {
                            titleEl.textContent = 'No matching tasks in this column';
                            if (subtitleEl) subtitleEl.textContent = 'Try adjusting your search or filters';
                        } else {
                            titleEl.textContent = status === 'todo' ? 'All caught up!' : status === 'doing' ? 'Nothing in progress' : 'No completed tasks yet';
                            if (subtitleEl) {
                                subtitleEl.textContent = status === 'todo' ? 'No tasks to do right now' : status === 'doing' ? 'Drag a task here to start working' : 'Drag finished tasks here to celebrate';
                            }
                        }
                    }
                } else {
                    emptyState.style.display = 'none';
                }
            }
        }
    });

    // Update quadrant counters and empty-state placeholders (Eisenhower Matrix)
    const quadrants = ['q1', 'q2', 'q3', 'q4'];
    quadrants.forEach((q) => {
        const list = document.getElementById(`list-${q}`);
        const badge = document.getElementById(`count-${q}`);
        const emptyState = document.getElementById(`empty-${q}`);

        if (list) {
            const visibleInQuad = list.querySelectorAll('.task-card:not([style*="display: none"])');
            const totalInQuad = list.querySelectorAll('.task-card');

            if (badge) badge.textContent = visibleInQuad.length;

            if (emptyState) {
                if (visibleInQuad.length === 0) {
                    emptyState.style.display = 'block';
                    const p = emptyState.querySelector('p');
                    if (p) {
                        const isFiltered = Boolean(query || priority || assignee);
                        if (isFiltered && totalInQuad.length > 0) {
                            p.textContent = 'No matching tasks in this quadrant';
                        } else {
                            const defaultMsgs = {
                                'q1': 'No urgent & important tasks',
                                'q2': 'No scheduled important tasks',
                                'q3': 'No delegated tasks',
                                'q4': 'No low-priority tasks'
                            };
                            p.textContent = defaultMsgs[q] || 'No tasks';
                        }
                    }
                } else {
                    emptyState.style.display = 'none';
                }
            }
        }
    });

    // Toggle Clear Filters button
    const isFiltered = Boolean(query || priority || assignee);
    if (clearBtn) {
        clearBtn.style.display = isFiltered ? 'inline-flex' : 'none';
    }

    // Update Filter Result Info Badge
    if (filterInfo) {
        if (isFiltered) {
            filterInfo.textContent = `Showing ${visibleCount} of ${cards.length} tasks`;
            filterInfo.style.display = 'inline-block';
        } else {
            filterInfo.style.display = 'none';
        }
    }
}

/**
 * Initializes quick assignee selector right on the task card:
 * Allows assigning or reassigning any task to any registered user directly
 * from the Kanban board with instant asynchronous persistence.
 */
function initQuickAssignee() {
    document.addEventListener('change', async (e) => {
        const select = e.target;
        if (!select.classList.contains('assignee-quick-select')) return;

        const taskId = select.dataset.taskId;
        const newAssigneeId = select.value ? parseInt(select.value, 10) : null;
        const card = select.closest('.task-card');
        const taskTitle = card?.querySelector('.task-title')?.textContent?.trim() || 'Task';
        const selectedOption = select.options[select.selectedIndex];
        const assigneeName = selectedOption ? selectedOption.text.trim() : 'Unassigned';

        select.classList.add('is-updating');

        try {
            const response = await fetch(`/api/tasks/${taskId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ assigned_to: newAssigneeId })
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Failed to update assignee.');
            }

            if (card) {
                card.dataset.assigneeId = newAssigneeId ? String(newAssigneeId) : '';
                card.dataset.assigneeName = assigneeName.toLowerCase();
            }

            showToast(`Assigned "${taskTitle}" to ${assigneeName}`, 'success');

            // Re-apply client filters so UI immediately reflects any active assignee filter
            applyClientFilters();

        } catch (err) {
            console.error('Assignee update failed:', err);
            showToast(`Failed to update assignee: ${err.message}`, 'error');
            // Revert select value from dataset
            if (card) {
                select.value = card.dataset.assigneeId || '';
            }
        } finally {
            select.classList.remove('is-updating');
        }
    });
}

/**
 * Intercepts manual status button submissions to perform asynchronous updates
 * as progressive enhancement without full page reload.
 */
function initAsyncStatusTransitions() {
    document.addEventListener('submit', async (e) => {
        const form = e.target;
        if (!form.matches || !form.matches('.card-status-actions form')) return;

        if (!window.fetch) return; // Fall back to normal form POST if fetch unsupported

        e.preventDefault();
        const actionUrl = form.getAttribute('action');
        const targetStatus = form.querySelector('input[name="status"]')?.value;
        const card = form.closest('.task-card');
        const taskId = card?.dataset?.taskId;
        const taskTitle = card?.querySelector('.task-title')?.textContent?.trim() || 'Task';

        if (!actionUrl || !targetStatus || !card) {
            form.submit();
            return;
        }

        try {
            const response = await fetch(actionUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ status: targetStatus })
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                form.submit();
                return;
            }

            // Move the card to target column list in the DOM
            const targetList = document.getElementById(`list-${targetStatus}`);
            if (targetList) {
                targetList.appendChild(card);
            }

            card.dataset.status = targetStatus;
            updateCardActionButtons(card, targetStatus, taskId);

            if (data.task) {
                updateCardUrgency(card, data.task);
            }

            updateColumnMetrics();
            applyClientFilters();
            showToast(`Moved "${taskTitle}" to ${formatStatusName(targetStatus)}`, 'success');

        } catch (err) {
            form.submit();
        }
    });
}

/**
 * Initializes Dark / Light Mode Toggle:
 * - Switches theme using CSS data-theme attribute on <html> element.
 * - Persists user preference in localStorage under 'taskmanager-theme'.
 * - Dispatches 'themeChanged' CustomEvent for real-time reactivity in Chart.js and other dynamic components.
 * - Synchronizes across browser tabs via storage events.
 */
function initThemeToggle() {
    const toggleButtons = document.querySelectorAll('#theme-toggle, .theme-toggle-btn');
    if (!toggleButtons.length) return;

    // Helper to update accessible labels and switch states based on current theme
    function updateAriaLabels(theme) {
        const nextTheme = theme === 'dark' ? 'light' : 'dark';
        const labelText = `Switch to ${nextTheme} mode`;
        toggleButtons.forEach((btn) => {
            btn.setAttribute('role', 'switch');
            btn.setAttribute('aria-checked', theme === 'dark' ? 'true' : 'false');
            btn.setAttribute('aria-label', labelText);
            btn.setAttribute('title', labelText);
        });
    }

    // Determine current theme from <html> or localStorage or system preference
    let currentTheme = document.documentElement.getAttribute('data-theme');
    if (!currentTheme) {
        try {
            const saved = localStorage.getItem('taskmanager-theme');
            const systemDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            currentTheme = saved ? saved : (systemDark ? 'dark' : 'light');
        } catch (e) {
            currentTheme = 'light';
        }
        document.documentElement.setAttribute('data-theme', currentTheme);
    }
    updateAriaLabels(currentTheme);

    // Click handler for toggle button(s)
    toggleButtons.forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const activeTheme = document.documentElement.getAttribute('data-theme') || 'light';
            const nextTheme = activeTheme === 'dark' ? 'light' : 'dark';

            // Apply new theme
            document.documentElement.setAttribute('data-theme', nextTheme);

            // Persist choice in localStorage
            try {
                localStorage.setItem('taskmanager-theme', nextTheme);
            } catch (err) {
                console.warn('Unable to persist theme to localStorage:', err);
            }

            // Update button labels
            updateAriaLabels(nextTheme);

            // Dispatch custom event for real-time subscribers (e.g. Chart.js redraws)
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: nextTheme } }));

            // Show subtle feedback toast
            if (typeof showToast === 'function') {
                showToast(`${nextTheme === 'dark' ? '🌙 Dark' : '☀️ Light'} mode activated`, 'info');
            }
        });
    });

    // Cross-tab synchronization
    window.addEventListener('storage', (e) => {
        if (e.key === 'taskmanager-theme' && e.newValue) {
            const newTheme = e.newValue;
            document.documentElement.setAttribute('data-theme', newTheme);
            updateAriaLabels(newTheme);
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: newTheme } }));
        }
    });
}

/**
 * Initializes SortableJS drag-and-drop across the 2x2 Eisenhower Matrix quadrants:
 * Q1: Urgent & Important ('q1')
 * Q2: Not Urgent & Important ('q2')
 * Q3: Urgent & Not Important ('q3')
 * Q4: Not Urgent & Not Important ('q4')
 */
function initSortableMatrix() {
    const matrixLists = document.querySelectorAll('#matrix-board-view .matrix-sortable-list');
    if (!matrixLists.length) return;

    if (typeof Sortable === 'undefined') {
        console.warn('SortableJS library not loaded. Eisenhower matrix drag and drop is disabled.');
        return;
    }

    matrixLists.forEach((list) => {
        new Sortable(list, {
            group: 'eisenhower-matrix',   // Drag between all 4 quadrants
            animation: 250,
            draggable: '.task-card',
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            dragClass: 'sortable-drag',
            filter: '.card-controls, .card-status-actions, .assignee-quick-select, a, button, input, textarea, select',
            preventOnFilter: false,

            async onEnd(evt) {
                const item = evt.item;
                const fromColumn = evt.from;
                const toColumn = evt.to;

                if (fromColumn === toColumn) return;

                const taskId = item.dataset.taskId;
                const targetQuadrant = toColumn.dataset.quadrant;
                const isUrgent = toColumn.dataset.urgent === 'true';
                const isImportant = toColumn.dataset.important === 'true';
                const taskTitle = item.querySelector('.task-title')?.textContent?.trim() || 'Task';

                if (!taskId || !targetQuadrant) return;

                // Optimistically update counts
                updateMatrixMetrics();

                try {
                    const response = await fetch(`/api/tasks/${taskId}`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        },
                        body: JSON.stringify({
                            quadrant: targetQuadrant,
                            urgent: isUrgent,
                            important: isImportant
                        })
                    });

                    const data = await response.json();
                    if (!response.ok || !data.success) {
                        throw new Error(data.error || 'Failed to update quadrant.');
                    }

                    // Update dataset on the moved card
                    item.dataset.quadrant = targetQuadrant;
                    item.dataset.important = String(isImportant);
                    if (data.task) {
                        item.dataset.isUrgent = String(data.task.is_urgent);
                        item.dataset.isOverdue = String(data.task.is_overdue);
                        item.dataset.isDueSoon = String(data.task.is_due_soon);
                        if (data.task.due_date) {
                            item.dataset.dueDate = data.task.due_date;
                        }

                        // Update urgency highlights and badges (overdue red / due <48h amber)
                        updateCardUrgency(item, data.task);

                        // Update important badge
                        updateCardImportantBadge(item, data.task.important);

                        // Update due date display
                        updateCardDueDate(item, data.task.due_date);
                    }

                    updateMatrixMetrics();
                    updateColumnMetrics();
                    applyClientFilters();

                    const quadrantTitles = {
                        'q1': 'Do First (Urgent & Important)',
                        'q2': 'Schedule (Not Urgent & Important)',
                        'q3': 'Delegate (Urgent & Not Important)',
                        'q4': "Don't Do (Not Urgent & Not Important)"
                    };
                    showToast(`Moved "${taskTitle}" to ${quadrantTitles[targetQuadrant] || targetQuadrant}`, 'success');

                } catch (err) {
                    console.error('Matrix quadrant move failed, reverting position:', err);
                    const originalNextSibling = fromColumn.children[evt.oldIndex] || null;
                    fromColumn.insertBefore(item, originalNextSibling);
                    updateMatrixMetrics();
                    applyClientFilters();
                    showToast(`Failed to update quadrant: ${err.message}`, 'error');
                }
            }
        });
    });

    updateMatrixMetrics();
}

/**
 * Updates or toggles the ⭐ Important badge on a card element.
 */
function updateCardImportantBadge(card, isImportant) {
    if (!card) return;
    const badgesContainer = card.querySelector('.card-badges');
    const existingBadge = card.querySelector('.badge-important');

    if (isImportant) {
        if (!existingBadge && badgesContainer) {
            const badge = document.createElement('span');
            badge.className = 'badge badge-important';
            badge.title = 'Important (Eisenhower Matrix)';
            badge.innerHTML = '⭐ Important';
            const priorityBadge = card.querySelector('.badge-priority');
            if (priorityBadge && priorityBadge.nextSibling) {
                badgesContainer.insertBefore(badge, priorityBadge.nextSibling);
            } else {
                badgesContainer.appendChild(badge);
            }
        }
    } else {
        if (existingBadge) {
            existingBadge.remove();
        }
    }
}

/**
 * Updates the due date text in the meta row of a card.
 */
function updateCardDueDate(card, dueDateStr) {
    if (!card) return;
    let metaDue = card.querySelector('.meta-due');
    if (!dueDateStr) {
        if (metaDue) metaDue.style.display = 'none';
        return;
    }

    if (!metaDue) {
        const metaContainer = card.querySelector('.task-meta');
        if (metaContainer) {
            metaDue = document.createElement('div');
            metaDue.className = 'meta-item meta-due';
            metaDue.title = 'Target Completion Date';
            metaDue.innerHTML = `<span>📅</span><span>${dueDateStr}</span>`;
            metaContainer.insertBefore(metaDue, metaContainer.firstChild);
        }
    }

    if (metaDue) {
        metaDue.style.display = '';
        const spans = metaDue.querySelectorAll('span');
        if (spans.length >= 2) {
            try {
                const parts = dueDateStr.split('-');
                if (parts.length === 3) {
                    const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
                    spans[1].textContent = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                } else {
                    spans[1].textContent = dueDateStr;
                }
            } catch (e) {
                spans[1].textContent = dueDateStr;
            }
        }
    }
}

/**
 * Updates quadrant count badges and empty-state placeholders in the 2x2 matrix.
 */
function updateMatrixMetrics() {
    const quadrants = ['q1', 'q2', 'q3', 'q4'];
    quadrants.forEach((q) => {
        const list = document.getElementById(`list-${q}`);
        const badge = document.getElementById(`count-${q}`);
        const emptyState = document.getElementById(`empty-${q}`);

        if (list) {
            const cards = list.querySelectorAll('.task-card');
            const visibleCards = list.querySelectorAll('.task-card:not([style*="display: none"])');
            const count = visibleCards.length;

            if (badge) badge.textContent = count;
            if (emptyState) {
                emptyState.style.display = count === 0 ? 'block' : 'none';
            }
        }
    });
}

/**
 * Distributes task cards into the 4 Eisenhower Matrix quadrants based on data-quadrant or (isUrgent, important).
 */
function distributeCardsToMatrix() {
    const cards = document.querySelectorAll('.task-card');
    cards.forEach(card => {
        let quad = card.dataset.quadrant;
        if (!quad || quad === 'undefined') {
            const isUrgent = card.dataset.isUrgent === 'true';
            const isImportant = card.dataset.important === 'true';
            if (isUrgent && isImportant) quad = 'q1';
            else if (!isUrgent && isImportant) quad = 'q2';
            else if (isUrgent && !isImportant) quad = 'q3';
            else quad = 'q4';
            card.dataset.quadrant = quad;
        }

        const targetList = document.getElementById(`list-${quad}`);
        if (targetList) {
            targetList.appendChild(card);
        }
    });
}

/**
 * Distributes task cards back into the 3 Kanban columns (todo, doing, done).
 */
function distributeCardsToKanban() {
    const cards = document.querySelectorAll('.task-card');
    cards.forEach(card => {
        const status = card.dataset.status || 'todo';
        const targetList = document.getElementById(`list-${status}`);
        if (targetList) {
            targetList.appendChild(card);
        }
    });
}

/**
 * Initializes the board view switcher (Kanban 3-column vs 2x2 Eisenhower Matrix).
 * Remembers user preference in localStorage under 'taskmanager-view-mode'.
 */
function initViewModeToggle() {
    const kanbanBtn = document.getElementById('toggle-view-kanban');
    const matrixBtn = document.getElementById('toggle-view-matrix');
    const kanbanBoard = document.getElementById('kanban-board-view');
    const matrixBoard = document.getElementById('matrix-board-view');

    if (!kanbanBtn || !matrixBtn || !kanbanBoard || !matrixBoard) return;

    let savedMode = 'kanban';
    try {
        savedMode = localStorage.getItem('taskmanager-view-mode') || 'kanban';
    } catch (e) {}

    function setView(mode) {
        if (mode === 'matrix') {
            distributeCardsToMatrix();
            kanbanBoard.style.display = 'none';
            matrixBoard.style.display = 'flex';
            kanbanBtn.classList.remove('active');
            matrixBtn.classList.add('active');
            updateMatrixMetrics();
        } else {
            distributeCardsToKanban();
            matrixBoard.style.display = 'none';
            kanbanBoard.style.display = 'grid';
            matrixBtn.classList.remove('active');
            kanbanBtn.classList.add('active');
            updateColumnMetrics();
        }

        try {
            localStorage.setItem('taskmanager-view-mode', mode);
        } catch (e) {}

        applyClientFilters();
    }

    kanbanBtn.addEventListener('click', (e) => {
        e.preventDefault();
        setView('kanban');
        showToast('Switched to 3-column Kanban view', 'info');
    });

    matrixBtn.addEventListener('click', (e) => {
        e.preventDefault();
        setView('matrix');
        showToast('Switched to 2x2 Eisenhower Matrix', 'info');
    });

    // Restore saved view preference
    if (savedMode === 'matrix') {
        setView('matrix');
    }
}

/**
 * Smooth count-up animation for numeric metric-value elements on page load (~800ms with easeOutQuart).
 *
 * @param {HTMLElement} element - Target DOM element displaying the number
 * @param {number} target - The final target number
 * @param {number} duration - Animation duration in ms (defaults to 800ms)
 * @param {string} suffix - Optional suffix string (e.g. '%')
 */
function animateCountUp(element, target, duration = 800, suffix = '') {
    if (!element) return;
    const targetVal = Number(target);
    if (isNaN(targetVal)) return;

    // Respect reduced motion accessibility
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        element.textContent = (Number.isInteger(targetVal) ? targetVal : targetVal.toFixed(1)) + suffix;
        return;
    }

    const startVal = 0;
    const startTime = performance.now();
    const isDecimal = !Number.isInteger(targetVal);

    // Quartic ease-out easing: f(t) = 1 - (1 - t)^4
    function easeOutQuart(t) {
        return 1 - Math.pow(1 - t, 4);
    }

    function step(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = easeOutQuart(progress);
        const current = startVal + (targetVal - startVal) * eased;

        element.textContent = (isDecimal ? current.toFixed(1) : Math.round(current)) + suffix;

        if (progress < 1) {
            requestAnimationFrame(step);
        } else {
            element.textContent = (isDecimal ? targetVal.toFixed(1) : targetVal) + suffix;
        }
    }

    requestAnimationFrame(step);
}

// Expose globally for cross-page use (e.g. in dashboard.html)
window.animateCountUp = animateCountUp;

/**
 * Automatically triggers count-up animation for all .metric-value elements present in the DOM on load.
 */
function initMetricCountUp() {
    const metricElements = document.querySelectorAll('.metric-value');
    metricElements.forEach((el) => {
        const raw = el.textContent.trim();
        if (!raw || raw === '-') return;
        const hasPercent = raw.endsWith('%');
        const numStr = raw.replace('%', '').trim();
        const num = parseFloat(numStr);
        if (!isNaN(num)) {
            animateCountUp(el, num, 800, hasPercent ? '%' : '');
        }
    });
}

/**
 * Initializes show/hide password toggle buttons on authentication forms.
 * Toggles input type between password and text, swaps SVG eye/eye-off icons,
 * and maintains proper ARIA accessibility attributes.
 */
function initPasswordToggle() {
    const toggleButtons = document.querySelectorAll('.btn-toggle-password');
    if (!toggleButtons.length) return;

    toggleButtons.forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const wrapper = btn.closest('.input-with-icon');
            if (!wrapper) return;

            const input = wrapper.querySelector('input');
            if (!input) return;

            const eyeIcon = btn.querySelector('.eye-icon');
            const eyeOffIcon = btn.querySelector('.eye-off-icon');

            const isPassword = input.getAttribute('type') === 'password';

            if (isPassword) {
                input.setAttribute('type', 'text');
                if (eyeIcon) eyeIcon.style.display = 'none';
                if (eyeOffIcon) eyeOffIcon.style.display = 'block';
                btn.setAttribute('aria-label', 'Hide password');
                btn.setAttribute('title', 'Hide password');
            } else {
                input.setAttribute('type', 'password');
                if (eyeIcon) eyeIcon.style.display = 'block';
                if (eyeOffIcon) eyeOffIcon.style.display = 'none';
                btn.setAttribute('aria-label', 'Show password');
                btn.setAttribute('title', 'Show password');
            }

            // Keep focus in the input for seamless user typing
            input.focus();
        });
    });
}

/**
 * Initializes loading spinner feedback on authentication form submit buttons.
 * When the user submits valid credentials, swaps the button label for a smooth
 * CSS spinner indicator to provide instant feedback and prevent accidental double-submits.
 */
function initAuthFormLoading() {
    const authForms = document.querySelectorAll('.auth-form');
    if (!authForms.length) return;

    authForms.forEach((form) => {
        form.addEventListener('submit', () => {
            // Respect HTML5 validation if present
            if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
                return;
            }

            const submitBtn = form.querySelector('.btn-auth-submit');
            if (!submitBtn) return;

            const btnText = submitBtn.querySelector('.btn-text');
            const btnSpinner = submitBtn.querySelector('.btn-spinner');

            submitBtn.classList.add('is-loading');
            if (btnText) btnText.style.display = 'none';
            if (btnSpinner) btnSpinner.style.display = 'inline-flex';

            // Disable interaction shortly after submit to avoid cancelling form post
            setTimeout(() => {
                submitBtn.style.pointerEvents = 'none';
            }, 20);
        });
    });
}

/**
 * Replaces the browser confirm() on task deletion with a custom animated modal
 * featuring backdrop blur and scale-in entrance.
 */
function initDeleteTaskModal() {
    const modal = document.getElementById('delete-task-modal');
    if (!modal) return;

    const modalTaskName = document.getElementById('modal-task-name');
    const modalDeleteForm = document.getElementById('modal-delete-form');
    const modalCloseBtn = document.getElementById('modal-delete-close');
    const modalCancelBtn = document.getElementById('modal-delete-cancel');
    let sourceFormToSubmit = null;

    function openModal(taskTitle, actionUrl, formElement = null) {
        if (modalTaskName) {
            modalTaskName.textContent = taskTitle ? `"${taskTitle}"` : 'this task';
        }
        sourceFormToSubmit = formElement;
        if (modalDeleteForm && actionUrl) {
            modalDeleteForm.action = actionUrl;
        }

        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';

        // Focus cancel button for keyboard navigation safety
        if (modalCancelBtn) {
            setTimeout(() => modalCancelBtn.focus(), 60);
        }
    }

    function closeModal() {
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
        sourceFormToSubmit = null;
    }

    // Close on cancel buttons
    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
    if (modalCancelBtn) modalCancelBtn.addEventListener('click', closeModal);

    // Close when clicking directly on the backdrop outside the modal dialog
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('is-open')) {
            closeModal();
        }
    });

    // Intercept delete trigger clicks across the board view, matrix view, and edit form
    document.addEventListener('click', (e) => {
        const deleteTrigger = e.target.closest('.btn-delete-task-trigger, .btn-icon-delete');
        if (!deleteTrigger) return;

        e.preventDefault();

        const form = deleteTrigger.closest('form');
        const card = deleteTrigger.closest('.task-card');
        
        let taskTitle = deleteTrigger.getAttribute('data-task-title');
        let actionUrl = deleteTrigger.getAttribute('data-delete-url');

        if (!taskTitle && form) {
            taskTitle = form.getAttribute('data-task-title');
        }
        if (!taskTitle && card) {
            const titleEl = card.querySelector('.task-title');
            if (titleEl) taskTitle = titleEl.textContent.trim();
        }

        if (!actionUrl && form) {
            actionUrl = form.action;
        }

        openModal(taskTitle, actionUrl, form);
    });

    // Handle confirm deletion submission
    if (modalDeleteForm) {
        modalDeleteForm.addEventListener('submit', (e) => {
            const confirmBtn = document.getElementById('modal-delete-confirm');
            if (confirmBtn) {
                confirmBtn.disabled = true;
                confirmBtn.innerHTML = `
                    <span class="spinner-ring" style="width: 14px; height: 14px; border-width: 2px;"></span>
                    <span>Deleting...</span>
                `;
            }

            // If an underlying source form was triggering, submit that, otherwise let modalDeleteForm post
            if (sourceFormToSubmit && sourceFormToSubmit !== modalDeleteForm) {
                e.preventDefault();
                sourceFormToSubmit.submit();
            }
        });
    }
}

/**
 * Initializes Mobile Navbar Hamburger Collapse / Expand:
 * - Toggles 'nav-menu-open' on #navbar-menu and 'is-active' on #nav-toggle.
 * - Updates aria-expanded attribute dynamically for screen readers.
 * - Closes dropdown when clicking outside, clicking a navigation link, or pressing Escape.
 */
function initNavbarToggle() {
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('navbar-menu');
    if (!navToggle || !navMenu) return;

    function openMenu() {
        navToggle.classList.add('is-active');
        navToggle.setAttribute('aria-expanded', 'true');
        navMenu.classList.add('nav-menu-open');
    }

    function closeMenu() {
        navToggle.classList.remove('is-active');
        navToggle.setAttribute('aria-expanded', 'false');
        navMenu.classList.remove('nav-menu-open');
    }

    navToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = navMenu.classList.contains('nav-menu-open');
        if (isOpen) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    // Close when clicking outside of navbar
    document.addEventListener('click', (e) => {
        if (!navMenu.contains(e.target) && !navToggle.contains(e.target)) {
            closeMenu();
        }
    });

    // Close when pressing Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && navMenu.classList.contains('nav-menu-open')) {
            closeMenu();
            navToggle.focus();
        }
    });

    // Close when clicking a nav link
    const navLinks = navMenu.querySelectorAll('.nav-link, .btn');
    navLinks.forEach((link) => {
        link.addEventListener('click', () => {
            closeMenu();
        });
    });
}

/**
 * Natural Language Quick-Add Bar with Live Parsed Preview:
 * - Real-time parsing via /api/tasks/parse using Python regex and dateparser
 * - Debounced preview with dynamic chips for Title, Due Date, Priority, Assignee, and Importance
 * - Instant creation via /api/tasks/quick-add with celebratory feedback
 */
function initQuickAddBar() {
    const form = document.getElementById('quick-add-form');
    const input = document.getElementById('quick-add-input');
    const clearBtn = document.getElementById('quick-add-clear-btn');
    const submitBtn = document.getElementById('quick-add-submit-btn');
    const preview = document.getElementById('quick-add-preview');

    if (!form || !input) return;

    // Check for stored toast message after reload
    try {
        const storedToast = sessionStorage.getItem('taskmanager-flash-toast');
        if (storedToast) {
            sessionStorage.removeItem('taskmanager-flash-toast');
            const data = JSON.parse(storedToast);
            if (data && data.message) {
                showToast(data.message, data.type || 'success');
            }
        }
    } catch (e) {}

    // Preview elements
    const chipTitle = document.getElementById('preview-chip-title');
    const valTitle = document.getElementById('preview-val-title');

    const chipDate = document.getElementById('preview-chip-date');
    const valDate = document.getElementById('preview-val-date');

    const chipPriority = document.getElementById('preview-chip-priority');
    const valPriority = document.getElementById('preview-val-priority');
    const iconPriority = document.getElementById('preview-icon-priority');

    const chipAssignee = document.getElementById('preview-chip-assignee');
    const valAssignee = document.getElementById('preview-val-assignee');

    const chipImportant = document.getElementById('preview-chip-important');

    let debounceTimer = null;
    let abortController = null;

    function renderPreview(parsed) {
        if (!parsed) {
            if (preview) preview.style.display = 'none';
            return;
        }

        if (preview) preview.style.display = 'flex';

        // 1. Title
        if (valTitle) {
            valTitle.textContent = parsed.title || 'Untitled Task';
        }

        // 2. Due Date
        if (chipDate && valDate) {
            if (parsed.due_date_human) {
                valDate.textContent = parsed.due_date_human;
                chipDate.style.display = 'inline-flex';
            } else {
                chipDate.style.display = 'none';
            }
        }

        // 3. Priority
        if (chipPriority && valPriority) {
            const prio = parsed.priority || 'medium';
            valPriority.textContent = parsed.priority_label || (prio.charAt(0).toUpperCase() + prio.slice(1));
            chipPriority.classList.remove('priority-high', 'priority-medium', 'priority-low');
            chipPriority.classList.add(`priority-${prio}`);

            if (iconPriority) {
                if (prio === 'high') iconPriority.textContent = '🔴';
                else if (prio === 'low') iconPriority.textContent = '🟢';
                else iconPriority.textContent = '🟡';
            }
        }

        // 4. Assignee
        if (chipAssignee && valAssignee) {
            if (parsed.assignee_name) {
                if (parsed.assignee_found) {
                    valAssignee.textContent = parsed.assignee_name;
                    chipAssignee.title = `Assigned to ${parsed.assignee_name}`;
                } else {
                    valAssignee.textContent = `${parsed.assignee_raw || parsed.assignee_name} (new)`;
                    chipAssignee.title = 'Assignee not yet in system';
                }
                chipAssignee.style.display = 'inline-flex';
            } else {
                chipAssignee.style.display = 'none';
            }
        }

        // 5. Important
        if (chipImportant) {
            chipImportant.style.display = parsed.important ? 'inline-flex' : 'none';
        }
    }

    async function fetchParsePreview(text) {
        if (abortController) {
            abortController.abort();
        }
        abortController = new AbortController();

        try {
            const response = await fetch('/api/tasks/parse', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ text }),
                signal: abortController.signal
            });

            if (!response.ok) return;
            const data = await response.json();
            if (data.success && data.parsed) {
                renderPreview(data.parsed);
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error('Error parsing task preview:', err);
            }
        }
    }

    function handleInputChange() {
        const value = input.value.trim();

        if (!value) {
            if (clearBtn) clearBtn.style.display = 'none';
            if (submitBtn) submitBtn.disabled = true;
            if (preview) preview.style.display = 'none';
            if (abortController) abortController.abort();
            clearTimeout(debounceTimer);
            return;
        }

        if (clearBtn) clearBtn.style.display = 'block';
        if (submitBtn) submitBtn.disabled = false;

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            fetchParsePreview(value);
        }, 150);
    }

    input.addEventListener('input', handleInputChange);

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            input.value = '';
            handleInputChange();
            input.focus();
        });
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const value = input.value.trim();
        if (!value) return;

        const btnText = submitBtn.querySelector('.quick-add-btn-text');
        const spinner = submitBtn.querySelector('.quick-add-spinner');

        submitBtn.disabled = true;
        if (btnText) btnText.textContent = 'Adding...';
        if (spinner) spinner.style.display = 'inline-block';

        try {
            const response = await fetch('/api/tasks/quick-add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ text: value })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                try {
                    sessionStorage.setItem('taskmanager-flash-toast', JSON.stringify({
                        message: `✨ ${result.message || 'Task created successfully!'}`,
                        type: 'success'
                    }));
                } catch (e) {}

                // Reload smoothly to update Kanban columns, metrics, Eisenhower matrix, and activity log
                window.location.reload();
            } else {
                showToast(result.error || 'Failed to create task.', 'error');
                submitBtn.disabled = false;
                if (btnText) btnText.textContent = 'Add Task';
                if (spinner) spinner.style.display = 'none';
            }
        } catch (err) {
            console.error('Error submitting quick task:', err);
            showToast('Network error while adding task. Please try again.', 'error');
            submitBtn.disabled = false;
            if (btnText) btnText.textContent = 'Add Task';
            if (spinner) spinner.style.display = 'none';
        }
    });
}

/**
 * Pomodoro Focus Timer with Start, Pause, Stop, and TimeLog Persistence
 * - 25-minute countdown session on active task
 * - Visual circular progress dial & status pills
 * - Web Audio API synthesized completion chime
 * - Asynchronously logs session to TimeLog database via POST /api/tasks/<id>/timelog
 * - Updates task card's total time spent badge in real time without full reload
 */
function initFocusTimer() {
    const modal = document.getElementById('focus-timer-modal');
    if (!modal) return;

    const modalTitle = document.getElementById('focus-modal-task-title');
    const display = document.getElementById('focus-time-display');
    const progressBar = document.getElementById('focus-progress-bar');
    const statusPill = document.getElementById('focus-status-pill');
    const hintText = document.getElementById('focus-timer-hint-text');

    const startBtn = document.getElementById('focus-btn-start');
    const startBtnText = document.getElementById('focus-btn-start-text');
    const pauseBtn = document.getElementById('focus-btn-pause');
    const stopBtn = document.getElementById('focus-btn-stop');
    const closeBtn = document.getElementById('focus-timer-close');

    const TOTAL_SECONDS = 25 * 60; // 25 minutes
    const CIRCLE_CIRCUMFERENCE = 490; // 2 * PI * 78

    let activeTaskId = null;
    let activeTaskTitle = '';
    let remainingSeconds = TOTAL_SECONDS;
    let timerInterval = null;
    let timerState = 'idle'; // 'idle', 'running', 'paused', 'finished'
    let originalDocumentTitle = document.title;

    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    function updateDisplay() {
        if (display) {
            display.textContent = formatTime(remainingSeconds);
        }
        if (progressBar) {
            const fraction = remainingSeconds / TOTAL_SECONDS;
            const offset = CIRCLE_CIRCUMFERENCE * (1 - fraction);
            progressBar.style.strokeDashoffset = offset;
        }
    }

    function playChime() {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const ctx = new AudioCtx();
            const now = ctx.currentTime;
            [523.25, 659.25, 783.99, 1046.50].forEach((freq, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.value = freq;
                gain.gain.setValueAtTime(0.18, now + i * 0.12);
                gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.12 + 0.9);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + i * 0.12);
                osc.stop(now + i * 0.12 + 0.9);
            });
        } catch (e) {}
    }

    function openModal(taskId, taskTitle) {
        activeTaskId = taskId;
        activeTaskTitle = taskTitle;
        if (modalTitle) modalTitle.textContent = taskTitle;

        resetTimer();
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('modal-open');
    }

    function closeModal() {
        if (timerState === 'running') {
            if (!confirm('A 25-minute focus session is currently in progress. Stop and close?')) {
                return;
            }
        }
        resetTimer();
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('modal-open');
        document.title = originalDocumentTitle;
    }

    function resetTimer() {
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = null;
        timerState = 'idle';
        remainingSeconds = TOTAL_SECONDS;
        updateDisplay();

        if (statusPill) {
            statusPill.textContent = 'Ready';
            statusPill.className = 'focus-status-pill';
        }
        if (hintText) {
            hintText.textContent = '💡 Stay focused on this task. Timer logs 25 minutes automatically upon completion.';
        }
        if (startBtn) {
            startBtn.style.display = 'inline-flex';
            if (startBtnText) startBtnText.textContent = '▶ Start';
        }
        if (pauseBtn) pauseBtn.style.display = 'none';
        if (stopBtn) stopBtn.style.display = 'inline-flex';
        if (progressBar) progressBar.style.stroke = '#f59e0b';
        document.title = originalDocumentTitle;
    }

    function startTimer() {
        if (timerState === 'finished') {
            resetTimer();
        }

        timerState = 'running';
        if (startBtn) startBtn.style.display = 'none';
        if (pauseBtn) pauseBtn.style.display = 'inline-flex';

        if (statusPill) {
            statusPill.textContent = 'Focusing...';
            statusPill.className = 'focus-status-pill status-running';
        }
        if (hintText) {
            hintText.textContent = '🔥 Deep focus in progress. Keep working!';
        }

        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            remainingSeconds--;
            updateDisplay();

            const timeStr = formatTime(remainingSeconds);
            document.title = `(${timeStr}) ${activeTaskTitle} • TaskManager`;

            if (remainingSeconds <= 0) {
                clearInterval(timerInterval);
                timerInterval = null;
                onFinished();
            }
        }, 1000);
    }

    function pauseTimer() {
        if (timerState !== 'running') return;
        timerState = 'paused';
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = null;

        if (pauseBtn) pauseBtn.style.display = 'none';
        if (startBtn) {
            startBtn.style.display = 'inline-flex';
            if (startBtnText) startBtnText.textContent = '▶ Resume';
        }

        if (statusPill) {
            statusPill.textContent = 'Paused';
            statusPill.className = 'focus-status-pill status-paused';
        }
        if (hintText) {
            hintText.textContent = '⏸ Session paused. Click Resume when you are ready to continue.';
        }
        document.title = `[Paused] ${activeTaskTitle} • TaskManager`;
    }

    async function saveTimeLog(taskId, minutes) {
        if (!taskId || minutes <= 0) return;
        try {
            const response = await fetch(`/api/tasks/${taskId}/timelog`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ duration_minutes: minutes })
            });

            const data = await response.json();
            if (response.ok && data.success) {
                // Update badge on task card
                updateCardTimeBadge(taskId, data.formatted_focus_time);
                if (typeof showToast === 'function') {
                    showToast(`⏱️ ${data.message || `${minutes}m logged successfully!`}`, 'success');
                }
            } else {
                if (typeof showToast === 'function') {
                    showToast(data.error || 'Failed to save focus time log.', 'error');
                }
            }
        } catch (err) {
            console.error('Error saving focus timelog:', err);
        }
    }

    function updateCardTimeBadge(taskId, formattedTime) {
        const badge = document.getElementById(`task-time-spent-${taskId}`);
        if (badge) {
            const valSpan = badge.querySelector('.time-spent-val');
            if (valSpan) valSpan.textContent = formattedTime;
            badge.style.display = 'inline-flex';
        }
    }

    function onFinished() {
        timerState = 'finished';
        playChime();

        if (statusPill) {
            statusPill.textContent = 'Completed! 🎉';
            statusPill.className = 'focus-status-pill status-completed';
        }
        if (progressBar) {
            progressBar.style.stroke = '#10b981';
        }
        if (hintText) {
            hintText.textContent = '🎉 Excellent job! 25 minutes logged on this task. Take a 5-minute break!';
        }

        if (pauseBtn) pauseBtn.style.display = 'none';
        if (startBtn) {
            startBtn.style.display = 'inline-flex';
            if (startBtnText) startBtnText.textContent = '↻ Start Another (25m)';
        }

        document.title = `🎉 Done! ${activeTaskTitle} • TaskManager`;

        // Save 25 minutes to TimeLog
        saveTimeLog(activeTaskId, 25);
    }

    function stopTimer() {
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = null;

        if (remainingSeconds < TOTAL_SECONDS && timerState !== 'finished') {
            const elapsed = TOTAL_SECONDS - remainingSeconds;
            const elapsedMinutes = Math.floor(elapsed / 60);

            if (elapsedMinutes >= 1) {
                if (confirm(`You completed ${elapsedMinutes} minute(s) of focus. Save this time to the task?`)) {
                    saveTimeLog(activeTaskId, elapsedMinutes);
                }
            }
        }

        resetTimer();
        closeModal();
    }

    // Attach event listeners for timer modal buttons
    if (startBtn) startBtn.addEventListener('click', startTimer);
    if (pauseBtn) pauseBtn.addEventListener('click', pauseTimer);
    if (stopBtn) stopBtn.addEventListener('click', stopTimer);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.style.display !== 'none') {
            closeModal();
        }
    });

    // Delegated click handler for "Start focus" buttons across task cards
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn-start-focus');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            const taskId = btn.dataset.taskId;
            const taskTitle = btn.dataset.taskTitle || 'Task Focus';
            openModal(taskId, taskTitle);
        }
    });
}

/**
 * Real-Time Multi-User Board Sync:
 * - Polls /api/changes?since=<timestamp> every 3 seconds (lightweight, no websockets)
 * - Updates task moves, edits, creations, and deletions live without page refresh
 * - Animates the changed card with a glowing pulse effect
 * - Displays small "Ravi moved this" / "Ravi edited this" avatar badges on updated cards
 */
function initLiveBoardSync() {
    const kanbanBoard = document.getElementById('kanban-board-view');
    const matrixBoard = document.getElementById('matrix-board-view');
    if (!kanbanBoard && !matrixBoard) return; // Only run on board views

    let lastTimestamp = new Date().toISOString();
    let isPolling = false;

    // Helper to display the live action avatar badge ("Ravi moved this")
    function showLiveAvatarBadge(card, initials, message) {
        if (!card) return;

        let badge = card.querySelector('.card-live-avatar-badge');
        if (!badge) {
            badge = document.createElement('div');
            badge.className = 'card-live-avatar-badge';
            badge.innerHTML = `
                <span class="live-avatar-initial">${initials || '?'}</span>
                <span class="live-avatar-msg">${message}</span>
            `;
            const titleEl = card.querySelector('.task-title');
            if (titleEl && titleEl.parentNode) {
                titleEl.parentNode.insertBefore(badge, titleEl);
            } else {
                card.prepend(badge);
            }
        } else {
            const initialEl = badge.querySelector('.live-avatar-initial');
            const msgEl = badge.querySelector('.live-avatar-msg');
            if (initialEl) initialEl.textContent = initials || '?';
            if (msgEl) msgEl.textContent = message;
            badge.style.display = 'inline-flex';
        }

        // Animate the card
        animateChangedCard(card);
    }

    function animateChangedCard(card) {
        if (!card) return;
        card.classList.remove('card-live-pulse');
        // Force DOM reflow to restart CSS animation cleanly
        void card.offsetWidth;
        card.classList.add('card-live-pulse');

        setTimeout(() => {
            card.classList.remove('card-live-pulse');
        }, 2200);
    }

    // Helper to dynamically build or clone a card for newly created tasks
    function createNewCardElement(task) {
        const anyCard = document.querySelector('.task-card');
        if (anyCard) {
            const clone = anyCard.cloneNode(true);
            clone.id = `task-card-${task.id}`;
            clone.dataset.taskId = task.id;
            clone.dataset.status = task.status || 'todo';
            clone.dataset.priority = task.priority || 'medium';
            clone.dataset.important = task.important ? 'true' : 'false';
            clone.dataset.isUrgent = task.is_urgent ? 'true' : 'false';
            clone.dataset.quadrant = task.eisenhower_quadrant || 'q4';
            clone.dataset.assigneeId = task.assigned_to || '';
            clone.dataset.assigneeName = (task.assignee_name || 'unassigned').toLowerCase();

            // Set classes
            clone.className = `task-card draggable-card priority-${task.priority || 'medium'}`;
            if (task.is_overdue) clone.classList.add('task-overdue');
            else if (task.is_due_soon) clone.classList.add('task-due-soon');

            // Title & description
            const titleEl = clone.querySelector('.task-title');
            if (titleEl) titleEl.textContent = task.title;

            let descEl = clone.querySelector('.task-description');
            if (task.description) {
                if (!descEl) {
                    descEl = document.createElement('p');
                    descEl.className = 'task-description';
                    if (titleEl && titleEl.nextSibling) {
                        titleEl.parentNode.insertBefore(descEl, titleEl.nextSibling);
                    }
                }
                descEl.textContent = task.description;
            } else if (descEl) {
                descEl.remove();
            }

            // Priority badge
            const prioBadge = clone.querySelector('.badge-priority');
            if (prioBadge) {
                prioBadge.className = `badge badge-priority badge-${task.priority}`;
                const prioDot = prioBadge.querySelector('.priority-dot');
                if (prioDot) prioDot.className = `priority-dot priority-dot-${task.priority}`;
                const prioText = prioBadge.lastChild;
                if (prioText) prioText.textContent = ` ${(task.priority || 'medium').charAt(0).toUpperCase() + (task.priority || 'medium').slice(1)}`;
            }

            // Important badge
            let impBadge = clone.querySelector('.badge-important');
            if (task.important) {
                if (!impBadge) {
                    impBadge = document.createElement('span');
                    impBadge.className = 'badge badge-important';
                    impBadge.title = 'Important (Eisenhower Matrix)';
                    impBadge.textContent = '⭐ Important';
                    const badgesWrap = clone.querySelector('.card-badges');
                    if (badgesWrap) badgesWrap.appendChild(impBadge);
                }
            } else if (impBadge) {
                impBadge.remove();
            }

            // Time spent badge
            const timeBadge = clone.querySelector('.badge-time-spent');
            if (timeBadge) {
                timeBadge.id = `task-time-spent-${task.id}`;
                if (task.total_focus_minutes > 0) {
                    const timeVal = timeBadge.querySelector('.time-spent-val');
                    if (timeVal) timeVal.textContent = task.formatted_focus_time || `${task.total_focus_minutes}m`;
                    timeBadge.style.display = 'inline-flex';
                } else {
                    timeBadge.style.display = 'none';
                }
            }

            // Update edit & delete links
            const editLink = clone.querySelector('.card-controls a.btn-icon');
            if (editLink) editLink.href = `/tasks/${task.id}/edit`;

            const delForm = clone.querySelector('.form-delete-task');
            if (delForm) {
                delForm.action = `/tasks/${task.id}/delete`;
                delForm.dataset.taskId = task.id;
                delForm.dataset.taskTitle = task.title;
            }

            // Focus button
            const focusBtn = clone.querySelector('.btn-start-focus');
            if (focusBtn) {
                focusBtn.dataset.taskId = task.id;
                focusBtn.dataset.taskTitle = task.title;
            }

            // Assignee dropdown
            const selectEl = clone.querySelector('.assignee-quick-select');
            if (selectEl) {
                selectEl.dataset.taskId = task.id;
                selectEl.value = task.assigned_to || '';
            }

            return clone;
        }
        return null;
    }

    async function pollChanges() {
        if (isPolling) return;
        if (document.hidden) return; // Save bandwidth when tab is backgrounded

        isPolling = true;
        try {
            const url = `/api/changes?since=${encodeURIComponent(lastTimestamp)}`;
            const response = await fetch(url, {
                headers: { 'Accept': 'application/json' }
            });

            if (!response.ok) {
                isPolling = false;
                return;
            }

            const data = await response.json();
            if (data.server_time) {
                lastTimestamp = data.server_time;
            }

            if (data.success && Array.isArray(data.changes) && data.changes.length > 0) {
                let metricsNeedUpdate = false;

                data.changes.forEach((change) => {
                    const taskId = change.task_id;
                    const action = change.action;
                    const userName = change.user_name || 'Someone';
                    const initials = change.user_initials || userName.charAt(0).toUpperCase();
                    const task = change.task;

                    let existingCard = document.getElementById(`task-card-${taskId}`);

                    if (action === 'deleted') {
                        if (existingCard) {
                            existingCard.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                            existingCard.style.opacity = '0';
                            existingCard.style.transform = 'scale(0.92)';
                            setTimeout(() => {
                                existingCard.remove();
                                updateColumnMetrics();
                            }, 300);
                            metricsNeedUpdate = true;
                        }
                    } else if (action === 'moved') {
                        if (existingCard && task) {
                            const newStatus = task.status;
                            const targetColList = document.getElementById(`list-${newStatus}`);

                            if (targetColList && existingCard.parentNode !== targetColList) {
                                targetColList.prepend(existingCard);
                                existingCard.dataset.status = newStatus;
                                metricsNeedUpdate = true;
                            }

                            // Show "Ravi moved this" avatar badge and animate
                            const message = `${userName} moved this`;
                            showLiveAvatarBadge(existingCard, initials, message);
                        }
                    } else if (action === 'edited') {
                        if (existingCard && task) {
                            // Update title
                            const titleEl = existingCard.querySelector('.task-title');
                            if (titleEl) titleEl.textContent = task.title;

                            // Update priority
                            existingCard.dataset.priority = task.priority;
                            const prioBadge = existingCard.querySelector('.badge-priority');
                            if (prioBadge) {
                                prioBadge.className = `badge badge-priority badge-${task.priority}`;
                                const prioDot = prioBadge.querySelector('.priority-dot');
                                if (prioDot) prioDot.className = `priority-dot priority-dot-${task.priority}`;
                                const prioText = prioBadge.lastChild;
                                if (prioText) prioText.textContent = ` ${task.priority.charAt(0).toUpperCase() + task.priority.slice(1)}`;
                            }

                            // Update important
                            existingCard.dataset.important = task.important ? 'true' : 'false';
                            let impBadge = existingCard.querySelector('.badge-important');
                            if (task.important) {
                                if (!impBadge) {
                                    impBadge = document.createElement('span');
                                    impBadge.className = 'badge badge-important';
                                    impBadge.title = 'Important (Eisenhower Matrix)';
                                    impBadge.textContent = '⭐ Important';
                                    const badgesWrap = existingCard.querySelector('.card-badges');
                                    if (badgesWrap) badgesWrap.appendChild(impBadge);
                                }
                            } else if (impBadge) {
                                impBadge.remove();
                            }

                            // Update assignee
                            if (task.assigned_to) {
                                existingCard.dataset.assigneeId = task.assigned_to;
                                existingCard.dataset.assigneeName = (task.assignee_name || '').toLowerCase();
                                const selectEl = existingCard.querySelector('.assignee-quick-select');
                                if (selectEl) selectEl.value = task.assigned_to;
                            }

                            // Show "Ravi edited this" avatar badge and animate
                            const message = `${userName} edited this`;
                            showLiveAvatarBadge(existingCard, initials, message);
                            metricsNeedUpdate = true;
                        }
                    } else if (action === 'added') {
                        if (!existingCard && task) {
                            const newCard = createNewCardElement(task);
                            if (newCard) {
                                const targetColList = document.getElementById(`list-${task.status || 'todo'}`);
                                if (targetColList) {
                                    targetColList.prepend(newCard);
                                    const message = `${userName} added this`;
                                    showLiveAvatarBadge(newCard, initials, message);
                                    metricsNeedUpdate = true;
                                }
                            }
                        }
                    }
                });

                if (metricsNeedUpdate && typeof updateColumnMetrics === 'function') {
                    updateColumnMetrics();
                }
            }
        } catch (err) {
            console.warn('Live sync poll error:', err);
        } finally {
            isPolling = false;
        }
    }

    // Start 3-second polling interval (no websockets, lightweight HTTP)
    setInterval(pollChanges, 3000);
}





