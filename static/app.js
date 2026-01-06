// OpenCode Session Manager - Application Script

let projects = [];
let sessions = [];
let selectedProjectId = null;
let selectedSessionId = null;
let multiSelectedProjects = new Set();
let multiSelectedSessions = new Set();
let selectionMode = null;
let isGlobalSearch = false;
let previewMessages = [];
let previewMatchIndex = -1;
let previewMatchCount = 0;

// Git config state for pending operations
let pendingGitConfigOperation = null;

document.addEventListener('DOMContentLoaded', async () => {
    await loadTheme();
    await checkStoragePath();
    await updateUndoButton();
});

async function loadTheme() {
    try {
        const data = await api('/theme');
        const theme = data.theme || 'default';
        document.documentElement.setAttribute('data-theme', theme);
        const selector = document.getElementById('themeSelect');
        if (selector) selector.value = theme;
    } catch (e) {
        console.error('Failed to load theme:', e);
        document.documentElement.setAttribute('data-theme', 'default');
    }
}

async function changeTheme(themeName) {
    document.documentElement.setAttribute('data-theme', themeName);
    try {
        await api('/theme', {
            method: 'POST',
            body: JSON.stringify({ theme: themeName })
        });
    } catch (e) {
        console.error('Failed to save theme:', e);
    }
}

async function api(endpoint, options = {}) {
    const response = await fetch('/api' + endpoint, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'API error');
    }
    return response.json();
}

async function checkStoragePath() {
    try {
        const data = await api('/storage-path');
        document.getElementById('storagePath').value = data.path;
        updateStatus(data.valid);
        if (data.valid) await loadProjects();
    } catch (e) {
        console.error(e);
        updateStatus(false);
    }
}

async function loadStoragePath() {
    const path = document.getElementById('storagePath').value.trim();
    if (!path) return;
    try {
        const data = await api('/storage-path', {
            method: 'POST',
            body: JSON.stringify({ path }),
        });
        updateStatus(data.valid);
        if (data.valid) await loadProjects();
    } catch (e) {
        alert('Error: ' + e.message);
        updateStatus(false);
    }
}

async function browsePath() {
    try {
        const data = await api('/browse');
        if (data.path) {
            document.getElementById('storagePath').value = data.path;
            await loadStoragePath();
        }
    } catch (e) {
        alert('Error opening file browser: ' + e.message);
    }
}

async function refresh() {
    await checkStoragePath();
    if (selectedProjectId) await loadSessions(selectedProjectId);
    if (selectedSessionId) {
        await loadPreview(selectedSessionId);
        await loadStats(selectedSessionId);
    }
}

async function shutdownApp() {
    try {
        await api('/shutdown', { method: 'POST' });
    } catch (e) {
        // Server is already shutting down, this is expected
    }
    window.close();
    // If window.close() didn't work, show shutdown message
    document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#888;font-size:1.2rem;">Application has been shut down. You can close this tab.</div>';
}

function updateStatus(valid) {
    document.getElementById('statusDot').className = 'status-dot ' + (valid ? 'valid' : 'invalid');
    document.getElementById('statusText').textContent = valid ? 'Connected' : 'Not connected';
}

async function loadProjects(search = '') {
    try {
        const data = await api('/projects?search=' + encodeURIComponent(search));
        projects = data.projects;
        renderProjects();
    } catch (e) { console.error(e); }
}

function renderProjects() {
    const container = document.getElementById('projectList');
    if (projects.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No projects found</p></div>';
        return;
    }
    const needsFixCount = projects.filter(p => p.needs_fix).length;
    container.innerHTML = projects.map(p => {
        const selected = p.id === selectedProjectId ? 'selected' : '';
        const multi = multiSelectedProjects.has(p.id) ? 'multi-selected' : '';
        const needsFixBadge = p.needs_fix ? '<span class="badge warning" title="Missing OpenCode fields - edit to fix">!</span>' : '';
        return `<div class="list-item project-item ${selected} ${multi}" data-id="${p.id}" 
            onclick="selectProject('${p.id}', event)"
            ondragover="onProjectDragOver(event, '${p.id}')"
            ondragleave="onProjectDragLeave(event)"
            ondrop="onProjectDrop(event, '${p.id}')">
            <div class="title">${escapeHtml(p.name)}${needsFixBadge}</div>
            <div class="subtitle">${escapeHtml(p.worktree || 'No path')}</div>
            <span class="badge">${p.session_count} sessions</span></div>`;
    }).join('');
    updateFixAllButton(needsFixCount);
}

async function selectProject(projectId, event) {
    if (event.ctrlKey || event.metaKey) {
        if (selectionMode === 'sessions') multiSelectedSessions.clear();
        selectionMode = 'projects';
        if (multiSelectedProjects.has(projectId)) multiSelectedProjects.delete(projectId);
        else multiSelectedProjects.add(projectId);
        renderProjects();
        renderSessions();
    } else {
        multiSelectedProjects.clear();
        multiSelectedSessions.clear();
        selectionMode = null;
        selectedProjectId = projectId;
        selectedSessionId = null;
        isGlobalSearch = false;
        // Clear session search when selecting a project
        document.getElementById('sessionSearch').value = '';
        renderProjects();
        await loadSessions(projectId);
        clearPreviewState();
    }
    updateButtons();
}

function clearPreviewState() {
    previewMessages = [];
    previewMatchIndex = -1;
    previewMatchCount = 0;
    document.getElementById('previewContent').innerHTML = '<div class="empty-state"><p>Select a session to preview</p></div>';
    document.getElementById('statsContent').innerHTML = '<div class="empty-state"><p>Select a session</p></div>';
    const searchInput = document.getElementById('previewSearch');
    if (searchInput) {
        searchInput.value = '';
        searchInput.disabled = true;
        searchInput.classList.remove('has-nav');
    }
    const navContainer = document.getElementById('previewSearchNav');
    if (navContainer) navContainer.classList.remove('visible');
    updatePreviewSearchClearButton();
}

async function loadSessions(projectId, search = '') {
    try {
        const data = await api('/projects/' + projectId + '/sessions?search=' + encodeURIComponent(search));
        sessions = data.sessions;
        isGlobalSearch = false;
        renderSessions();
    } catch (e) { console.error(e); }
}

function renderSessions() {
    const container = document.getElementById('sessionList');
    const searchTerm = document.getElementById('sessionSearch').value.trim();
    
    if (!selectedProjectId && !isGlobalSearch) {
        container.innerHTML = '<div class="empty-state"><p>Select a project or search</p></div>';
        return;
    }
    if (sessions.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No sessions found</p></div>';
        return;
    }
    container.innerHTML = sessions.map(s => {
        const selected = s.id === selectedSessionId ? 'selected' : '';
        const multi = multiSelectedSessions.has(s.id) ? 'multi-selected' : '';
        const projectId = s.project_id || selectedProjectId;
        const projectBadge = isGlobalSearch && s.project_name 
            ? `<span class="badge project-badge">${escapeHtml(s.project_name)}</span>` 
            : '';
        return `<div class="list-item session-item ${selected} ${multi}" data-id="${s.id}" data-project-id="${projectId}" draggable="true" onclick="selectSession('${s.id}', event, '${projectId}')">
            <div class="title">${escapeHtml(s.title || s.id)}${projectBadge}</div>
            <div class="subtitle">${formatDate(s.updated || s.created)}</div></div>`;
    }).join('');
    initSortable();
}

async function selectSession(sessionId, event, projectId = null) {
    if (event.ctrlKey || event.metaKey) {
        if (selectionMode === 'projects') multiSelectedProjects.clear();
        selectionMode = 'sessions';
        if (multiSelectedSessions.has(sessionId)) multiSelectedSessions.delete(sessionId);
        else multiSelectedSessions.add(sessionId);
        renderProjects();
        renderSessions();
    } else {
        multiSelectedProjects.clear();
        multiSelectedSessions.clear();
        selectionMode = null;
        selectedSessionId = sessionId;
        
        // If in global search and we have a project ID, highlight the corresponding project
        if (isGlobalSearch && projectId) {
            selectedProjectId = projectId;
            renderProjects();
        }
        
        renderSessions();
        await loadPreview(sessionId);
        await loadStats(sessionId);
    }
    updateButtons();
}

async function loadPreview(sessionId) {
    const container = document.getElementById('previewContent');
    const searchInput = document.getElementById('previewSearch');
    container.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';
    
    previewMatchIndex = -1;
    previewMatchCount = 0;
    
    if (searchInput) {
        searchInput.disabled = true;
        searchInput.value = '';
        searchInput.classList.remove('has-nav');
    }
    updatePreviewSearchClearButton();
    updatePreviewNavigation();
    
    try {
        const data = await api('/sessions/' + sessionId + '/preview');
        previewMessages = data.messages;
        if (previewMessages.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No messages found</p></div>';
            return;
        }
        if (searchInput) searchInput.disabled = false;
        renderPreview();
    } catch (e) {
        previewMessages = [];
        container.innerHTML = '<div class="empty-state"><p>Error: ' + escapeHtml(e.message) + '</p></div>';
    }
}

function renderPreview(searchTerm = '') {
    const container = document.getElementById('previewContent');
    
    if (previewMessages.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No messages found</p></div>';
        updatePreviewNavigation();
        return;
    }
    
    let matchIndex = 0;
    previewMatchCount = 0;
    
    container.innerHTML = previewMessages.map(m => {
        let content = escapeHtml(m.content);
        if (searchTerm) {
            const result = highlightTextWithIndex(content, searchTerm, matchIndex);
            content = result.text;
            matchIndex = result.nextIndex;
        }
        return `<div class="message ${m.role}">
            <div class="role">${escapeHtml(m.role)}</div>
            <div class="content">${content}</div></div>`;
    }).join('');
    
    previewMatchCount = matchIndex;
    updatePreviewNavigation();
    
    // Auto-select first match if searching
    if (searchTerm && previewMatchCount > 0 && previewMatchIndex === -1) {
        previewMatchIndex = 0;
        highlightCurrentMatch();
    }
}

function highlightTextWithIndex(text, searchTerm, startIndex) {
    if (!searchTerm) return { text, nextIndex: startIndex };
    const escapedSearch = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedSearch})`, 'gi');
    let index = startIndex;
    const result = text.replace(regex, (match) => {
        return `<mark data-match-index="${index++}">${match}</mark>`;
    });
    return { text: result, nextIndex: index };
}

function filterPreview() {
    const searchTerm = document.getElementById('previewSearch').value.trim();
    updatePreviewSearchClearButton();
    previewMatchIndex = -1;
    renderPreview(searchTerm);
}

function updatePreviewNavigation() {
    const navContainer = document.getElementById('previewSearchNav');
    const countDisplay = document.getElementById('previewMatchCount');
    const searchInput = document.getElementById('previewSearch');
    
    if (!navContainer || !countDisplay || !searchInput) return;
    
    if (previewMatchCount > 0) {
        navContainer.classList.add('visible');
        searchInput.classList.add('has-nav');
        countDisplay.textContent = `${previewMatchIndex + 1}/${previewMatchCount}`;
    } else {
        navContainer.classList.remove('visible');
        searchInput.classList.remove('has-nav');
        countDisplay.textContent = '';
    }
}

function highlightCurrentMatch() {
    // Remove previous current highlight
    document.querySelectorAll('#previewContent mark.current').forEach(el => {
        el.classList.remove('current');
    });
    
    // Add current highlight and scroll to it
    const currentMark = document.querySelector(`#previewContent mark[data-match-index="${previewMatchIndex}"]`);
    if (currentMark) {
        currentMark.classList.add('current');
        currentMark.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    updatePreviewNavigation();
}

function prevMatch() {
    if (previewMatchCount === 0) return;
    previewMatchIndex = (previewMatchIndex - 1 + previewMatchCount) % previewMatchCount;
    highlightCurrentMatch();
}

function nextMatch() {
    if (previewMatchCount === 0) return;
    previewMatchIndex = (previewMatchIndex + 1) % previewMatchCount;
    highlightCurrentMatch();
}

function updatePreviewSearchClearButton() {
    const searchInput = document.getElementById('previewSearch');
    const clearBtn = document.getElementById('previewSearchClear');
    if (!searchInput || !clearBtn) return;
    
    if (searchInput.value.length > 0) {
        clearBtn.classList.add('visible');
    } else {
        clearBtn.classList.remove('visible');
    }
}

function clearPreviewSearch() {
    document.getElementById('previewSearch').value = '';
    previewMatchIndex = -1;
    previewMatchCount = 0;
    updatePreviewSearchClearButton();
    renderPreview();
}

function handlePreviewSearchKey(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        if (event.shiftKey) {
            prevMatch();
        } else {
            nextMatch();
        }
    }
}

async function loadStats(sessionId) {
    const container = document.getElementById('statsContent');
    try {
        const data = await api('/sessions/' + sessionId + '/stats');
        container.innerHTML = `
            <div class="stat-item"><div class="label">Session ID</div><div class="value" style="font-size:0.8rem;word-break:break-all;">${escapeHtml(data.session_id)}</div></div>
            <div class="stat-item"><div class="label">Messages</div><div class="value">${data.message_count}</div></div>
            <div class="stat-item"><div class="label">Total Size</div><div class="value">${formatSize(data.total_size)}</div></div>
            <div class="stat-item"><div class="label">Created</div><div class="value">${formatDate(data.created)}</div></div>
            <div class="stat-item"><div class="label">Last Modified</div><div class="value">${formatDate(data.updated)}</div></div>
            <div class="stat-item"><div class="label">Has Diffs</div><div class="value">${data.has_diffs ? 'Yes' : 'No'}</div></div>
            <div class="stat-item"><div class="label">Has Todos</div><div class="value">${data.has_todos ? 'Yes' : 'No'}</div></div>`;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>Error: ' + escapeHtml(e.message) + '</p></div>';
    }
}

function filterProjects() { 
    updateProjectSearchClearButton();
    loadProjects(document.getElementById('projectSearch').value); 
}

function updateProjectSearchClearButton() {
    const searchInput = document.getElementById('projectSearch');
    const clearBtn = document.getElementById('projectSearchClear');
    if (searchInput.value.length > 0) {
        clearBtn.classList.add('visible');
    } else {
        clearBtn.classList.remove('visible');
    }
}

function clearProjectSearch() {
    document.getElementById('projectSearch').value = '';
    updateProjectSearchClearButton();
    filterProjects();
}

function filterSessions() {
    const searchTerm = document.getElementById('sessionSearch').value.trim();
    updateSearchClearButton();
    if (searchTerm) {
        // Always do global search when there's a search term
        loadGlobalSessions(searchTerm);
    } else if (selectedProjectId) {
        // No search term, show sessions for selected project
        isGlobalSearch = false;
        loadSessions(selectedProjectId, '');
    } else {
        // No search term and no project selected
        isGlobalSearch = false;
        sessions = [];
        renderSessions();
    }
}

function updateSearchClearButton() {
    const searchInput = document.getElementById('sessionSearch');
    const clearBtn = document.getElementById('sessionSearchClear');
    if (searchInput.value.length > 0) {
        clearBtn.classList.add('visible');
    } else {
        clearBtn.classList.remove('visible');
    }
}

function clearSessionSearch() {
    document.getElementById('sessionSearch').value = '';
    updateSearchClearButton();
    filterSessions();
}

async function loadGlobalSessions(search) {
    try {
        const data = await api('/sessions/search?search=' + encodeURIComponent(search));
        sessions = data.sessions;
        isGlobalSearch = true;
        renderSessions();
    } catch (e) { console.error(e); }
}

function initSortable() {
    if (typeof Sortable === 'undefined') return;
    const sessionList = document.getElementById('sessionList');
    if (sessionList._sortable) sessionList._sortable.destroy();
    sessionList._sortable = new Sortable(sessionList, {
        group: 'sessions', animation: 150,
        ghostClass: 'sortable-ghost', dragClass: 'sortable-drag'
    });
}

function onProjectDragOver(event, projectId) {
    event.preventDefault();
    event.currentTarget.classList.add('drag-over');
}
function onProjectDragLeave(event) { event.currentTarget.classList.remove('drag-over'); }

async function onProjectDrop(event, targetProjectId) {
    event.preventDefault();
    event.currentTarget.classList.remove('drag-over');
    const draggedElement = document.querySelector('.session-item.sortable-drag, .session-item[draggable="true"]:active');
    const sessionId = draggedElement?.dataset?.id || selectedSessionId;
    if (!sessionId || targetProjectId === selectedProjectId) return;
    try {
        await api('/sessions/move', {
            method: 'POST',
            body: JSON.stringify({ session_id: sessionId, target_project_id: targetProjectId }),
        });
        await loadProjects();
        await loadSessions(selectedProjectId);
        updateUndoButton();
    } catch (e) { alert('Error moving session: ' + e.message); }
}

function updateButtons() {
    const hasProjectSelection = multiSelectedProjects.size > 0 || (selectionMode !== 'sessions' && selectedProjectId);
    const hasSessionSelection = multiSelectedSessions.size > 0 || (selectionMode !== 'projects' && selectedSessionId);
    document.getElementById('deleteBtn').disabled = !hasProjectSelection && !hasSessionSelection;
    document.getElementById('editBtn').disabled = (multiSelectedProjects.size !== 1 && multiSelectedSessions.size !== 1 && !selectedProjectId && !selectedSessionId) ||
        (multiSelectedProjects.size > 1 || multiSelectedSessions.size > 1);
    // Check & Repair is only enabled when exactly one project is selected (not in session selection mode)
    const singleProjectSelected = selectedProjectId && !selectedSessionId && multiSelectedProjects.size <= 1 && selectionMode !== 'sessions';
    document.getElementById('checkRepairBtn').disabled = !singleProjectSelected;
}

function updateFixAllButton(needsFixCount) {
    const btn = document.getElementById('fixAllBtn');
    if (btn) {
        btn.style.display = needsFixCount > 0 ? 'inline-block' : 'none';
        btn.textContent = `Fix ${needsFixCount} Project${needsFixCount !== 1 ? 's' : ''}`;
        btn.title = `${needsFixCount} project(s) need fixing: missing git setup or OpenCode fields. Click to initialize git repos and migrate project IDs.`;
    }
}

async function fixAllProjects() {
    try {
        const result = await api('/projects/fix-all', { method: 'POST' });
        let message = '';
        if (result.count > 0) {
            message = `Fixed ${result.count} project(s):\n- ${result.fixed.join('\n- ')}`;
        } else {
            message = 'No projects needed fixing.';
        }
        if (result.errors && result.errors.length > 0) {
            message += `\n\nErrors (${result.errors.length}):\n`;
            message += result.errors.map(e => `- ${e.file}: ${e.error}`).join('\n');
        }
        alert(message);
        await loadProjects();
    } catch (e) {
        alert('Error fixing projects: ' + e.message);
    }
}

async function checkRepairProject(gitUserName = null, gitUserEmail = null) {
    const projectId = multiSelectedProjects.size === 1 ? [...multiSelectedProjects][0] : selectedProjectId;
    if (!projectId) {
        alert('Please select a project first.');
        return;
    }
    
    const project = projects.find(p => p.id === projectId);
    const projectName = project?.name || projectId;
    
    try {
        const payload = {};
        if (gitUserName && gitUserEmail) {
            payload.git_user_name = gitUserName;
            payload.git_user_email = gitUserEmail;
        }
        
        const result = await api(`/projects/${projectId}/check-repair`, { 
            method: 'POST',
            body: Object.keys(payload).length > 0 ? JSON.stringify(payload) : undefined
        });
        
        // Check if git config is needed
        if (result.needs_git_config) {
            pendingGitConfigOperation = {
                type: 'repair_project',
                projectId: projectId
            };
            showGitConfigModal();
            return;
        }
        
        let message = `Check & Repair Report for "${projectName}"\n`;
        message += '='.repeat(40) + '\n\n';
        
        if (result.new_project_id && result.new_project_id !== projectId) {
            message += `Project ID migrated:\n  ${projectId}\n  -> ${result.new_project_id}\n\n`;
        }
        
        if (result.issues_found.length > 0) {
            message += `Issues Found (${result.issues_found.length}):\n`;
            message += result.issues_found.map(i => `  - ${i}`).join('\n');
            message += '\n\n';
        } else {
            message += 'No issues found.\n\n';
        }
        
        if (result.fixes_applied.length > 0) {
            message += `Fixes Applied (${result.fixes_applied.length}):\n`;
            message += result.fixes_applied.map(f => `  - ${f}`).join('\n');
            message += '\n\n';
        }
        
        if (result.errors.length > 0) {
            message += `Errors (${result.errors.length}):\n`;
            message += result.errors.map(e => `  - ${e}`).join('\n');
            message += '\n';
        }
        
        if (result.issues_found.length === 0 && result.fixes_applied.length === 0 && result.errors.length === 0) {
            message += 'Project is healthy - no repairs needed!';
        }
        
        alert(message);
        
        // Reload projects since IDs may have changed
        await loadProjects();
        
        // If project ID changed, select the new one
        if (result.new_project_id && result.new_project_id !== projectId) {
            selectedProjectId = result.new_project_id;
            renderProjects();
            await loadSessions(result.new_project_id);
        } else if (selectedProjectId) {
            await loadSessions(selectedProjectId);
        }
        
    } catch (e) {
        alert('Error checking/repairing project: ' + e.message);
    }
}

function showDeleteModal() {
    const list = document.getElementById('deleteList');
    let items = [];
    
    // Determine what to delete based on selection state
    const hasMultiProjects = multiSelectedProjects.size > 0;
    const hasMultiSessions = multiSelectedSessions.size > 0;
    const hasSelectedProject = selectedProjectId && !selectedSessionId;
    const hasSelectedSession = selectedSessionId;
    
    if (hasMultiProjects || (selectionMode === 'projects')) {
        const ids = hasMultiProjects ? [...multiSelectedProjects] : [selectedProjectId];
        items = ids.filter(id => id).map(id => { const p = projects.find(x => x.id === id); return { type: 'Project', name: p?.name || id, id }; });
    } else if (hasMultiSessions || hasSelectedSession) {
        const ids = hasMultiSessions ? [...multiSelectedSessions] : [selectedSessionId];
        items = ids.filter(id => id).map(id => { const s = sessions.find(x => x.id === id); return { type: 'Session', name: s?.title || id, id }; });
    } else if (hasSelectedProject) {
        const p = projects.find(x => x.id === selectedProjectId);
        items = [{ type: 'Project', name: p?.name || selectedProjectId, id: selectedProjectId }];
    }
    
    list.innerHTML = items.map(item => `<div class="delete-list-item"><strong>${item.type}:</strong> ${escapeHtml(item.name)}</div>`).join('');
    document.getElementById('deleteModal').classList.add('active');
}

function closeDeleteModal() { document.getElementById('deleteModal').classList.remove('active'); }

async function confirmDelete() {
    try {
        const hasMultiProjects = multiSelectedProjects.size > 0;
        const hasMultiSessions = multiSelectedSessions.size > 0;
        const hasSelectedProject = selectedProjectId && !selectedSessionId;
        const hasSelectedSession = selectedSessionId;
        
        if (hasMultiProjects || selectionMode === 'projects' || (hasSelectedProject && !hasMultiSessions)) {
            const ids = hasMultiProjects ? [...multiSelectedProjects] : [selectedProjectId];
            await api('/projects', { method: 'DELETE', body: JSON.stringify({ ids: ids.filter(id => id) }) });
            multiSelectedProjects.clear();
            selectedProjectId = null;
            selectedSessionId = null;
            sessions = [];
            await loadProjects();
            renderSessions();
        } else if (hasMultiSessions || hasSelectedSession) {
            const ids = hasMultiSessions ? [...multiSelectedSessions] : [selectedSessionId];
            await api('/sessions', { method: 'DELETE', body: JSON.stringify({ ids: ids.filter(id => id) }) });
            multiSelectedSessions.clear();
            selectedSessionId = null;
            await loadSessions(selectedProjectId);
        }
        clearPreviewState();
        closeDeleteModal();
        updateButtons();
        updateUndoButton();
    } catch (e) { alert('Error deleting: ' + e.message); }
}

async function updateUndoButton() {
    try {
        const data = await api('/undo/status');
        document.getElementById('undoBtn').disabled = !data.available;
        document.getElementById('undoTooltip').textContent = data.available ? data.description : 'Nothing to undo';
    } catch (e) { console.error('Failed to update undo status:', e); }
}

async function performUndo() {
    try {
        const result = await api('/undo', { method: 'POST' });
        await loadProjects();
        if (selectedProjectId) await loadSessions(selectedProjectId);
        if (result.errors.length > 0) alert('Some items could not be restored: ' + result.errors.map(e => e.error).join(', '));
    } catch (e) { 
        alert('Undo failed: ' + e.message); 
    } finally {
        updateUndoButton();
    }
}

function showEditModal() {
    const input = document.getElementById('editInput');
    const worktreeField = document.getElementById('worktreeField');
    const worktreeInput = document.getElementById('editWorktree');
    
    if (selectionMode === 'projects' || multiSelectedProjects.size === 1 || (!selectionMode && selectedProjectId && !selectedSessionId)) {
        const projectId = multiSelectedProjects.size === 1 ? [...multiSelectedProjects][0] : selectedProjectId;
        const project = projects.find(p => p.id === projectId);
        document.getElementById('editModalTitle').textContent = 'Edit Project';
        document.getElementById('editNameLabel').textContent = 'Project Name';
        input.value = project?.name || '';
        input.dataset.type = 'project';
        input.dataset.id = projectId;
        worktreeField.style.display = 'block';
        worktreeInput.value = project?.worktree || '';
    } else {
        const sessionId = multiSelectedSessions.size === 1 ? [...multiSelectedSessions][0] : selectedSessionId;
        const session = sessions.find(s => s.id === sessionId);
        document.getElementById('editModalTitle').textContent = 'Edit Session';
        document.getElementById('editNameLabel').textContent = 'Session Title';
        input.value = session?.title || '';
        input.dataset.type = 'session';
        input.dataset.id = sessionId;
        worktreeField.style.display = 'none';
        worktreeInput.value = '';
    }
    document.getElementById('editModal').classList.add('active');
    input.focus();
    input.select();
}

async function browseWorktree() {
    try {
        const data = await api('/browse');
        if (data.path) {
            document.getElementById('editWorktree').value = data.path;
        }
    } catch (e) {
        alert('Error opening file browser: ' + e.message);
    }
}

function closeEditModal() { 
    document.getElementById('editModal').classList.remove('active');
    document.getElementById('worktreeField').style.display = 'none';
}

async function confirmEdit(gitUserName = null, gitUserEmail = null) {
    const input = document.getElementById('editInput');
    const newName = input.value.trim();
    if (!newName) { alert('Name cannot be empty'); return; }
    try {
        if (input.dataset.type === 'project') {
            const worktree = document.getElementById('editWorktree').value.trim();
            const payload = { new_name: newName, worktree: worktree };
            if (gitUserName && gitUserEmail) {
                payload.git_user_name = gitUserName;
                payload.git_user_email = gitUserEmail;
            }
            
            const result = await api('/projects/' + input.dataset.id + '/update', { 
                method: 'PUT', 
                body: JSON.stringify(payload) 
            });
            
            // Check if git config is needed
            if (result.needs_git_config) {
                pendingGitConfigOperation = {
                    type: 'update_project',
                    projectId: input.dataset.id,
                    newName: newName,
                    worktree: worktree
                };
                showGitConfigModal();
                return;
            }
            
            // Handle migration to new project ID
            if (result.migrated && result.new_project_id) {
                selectedProjectId = result.new_project_id;
                if (result.merged) {
                    alert(`Project merged into existing project "${result.target_project_name}".\n${result.sessions_moved} session(s) moved.`);
                } else {
                    alert(`Project migrated to new git repository.\n${result.sessions_moved} session(s) moved.`);
                }
            }
            
            await loadProjects();
            
            // Reload sessions for the (possibly new) project
            if (selectedProjectId) {
                await loadSessions(selectedProjectId);
            }
        } else {
            await api('/sessions/' + input.dataset.id + '/rename', { method: 'PUT', body: JSON.stringify({ new_name: newName }) });
            await loadSessions(selectedProjectId);
        }
        closeEditModal();
        updateUndoButton();
    } catch (e) { alert('Error saving: ' + e.message); }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(timestamp) {
    if (!timestamp) return 'Unknown';
    return new Date(timestamp).toLocaleString();
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function showAddProjectModal() {
    document.getElementById('newProjectName').value = '';
    document.getElementById('newProjectWorktree').value = '';
    document.getElementById('addProjectModal').classList.add('active');
    document.getElementById('newProjectName').focus();
}

function closeAddProjectModal() {
    document.getElementById('addProjectModal').classList.remove('active');
}

async function browseNewProjectWorktree() {
    try {
        const data = await api('/browse');
        if (data.path) {
            document.getElementById('newProjectWorktree').value = data.path;
        }
    } catch (e) {
        alert('Error opening file browser: ' + e.message);
    }
}

async function confirmAddProject(gitUserName = null, gitUserEmail = null) {
    const name = document.getElementById('newProjectName').value.trim();
    const worktree = document.getElementById('newProjectWorktree').value.trim();
    
    if (!name) {
        alert('Project name is required');
        return;
    }
    
    try {
        const payload = { name, worktree };
        if (gitUserName && gitUserEmail) {
            payload.git_user_name = gitUserName;
            payload.git_user_email = gitUserEmail;
        }
        
        const result = await api('/projects', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        
        // Check if git config is needed
        if (result.needs_git_config) {
            pendingGitConfigOperation = {
                type: 'create_project',
                name: name,
                worktree: worktree
            };
            showGitConfigModal();
            return;
        }
        
        closeAddProjectModal();
        await loadProjects();
        updateUndoButton();
        
        // Select the new project
        selectedProjectId = result.project_id;
        renderProjects();
        await loadSessions(result.project_id);
    } catch (e) {
        alert('Error creating project: ' + e.message);
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Delete' && !e.target.matches('input')) {
        if (!document.getElementById('deleteBtn').disabled) showDeleteModal();
    }
    if (e.key === 'Escape') { closeDeleteModal(); closeEditModal(); closeAddProjectModal(); closeScanOrphansModal(); }
    if (e.key === 'Enter' && document.getElementById('editModal').classList.contains('active')) confirmEdit();
    if (e.key === 'Enter' && document.getElementById('addProjectModal').classList.contains('active')) confirmAddProject();
    if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.target.matches('input')) {
        if (!document.getElementById('undoBtn').disabled) performUndo();
    }
});

// =============================================================================
// Orphan Scan Functions
// =============================================================================

let lastOrphanScanResult = null;

function showScanOrphansModal() {
    // Reset modal to initial state
    document.getElementById('scanOrphansTitle').textContent = 'Scan for Orphaned Data';
    document.getElementById('scanOrphansContent').style.display = 'block';
    document.getElementById('scanOrphansResults').style.display = 'none';
    document.getElementById('startScanBtn').style.display = 'inline-block';
    document.getElementById('cleanupOrphansBtn').style.display = 'none';
    lastOrphanScanResult = null;
    
    document.getElementById('scanOrphansModal').classList.add('active');
}

function closeScanOrphansModal() {
    document.getElementById('scanOrphansModal').classList.remove('active');
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

async function startOrphanScan() {
    const contentDiv = document.getElementById('scanOrphansContent');
    const resultsDiv = document.getElementById('scanOrphansResults');
    const startBtn = document.getElementById('startScanBtn');
    const cleanupBtn = document.getElementById('cleanupOrphansBtn');
    
    // Show scanning indicator
    contentDiv.innerHTML = '<div class="scanning-indicator"><span class="spinner"></span>Scanning storage folders... This may take a while.</div>';
    startBtn.disabled = true;
    startBtn.textContent = 'Scanning...';
    
    try {
        const result = await api('/orphans/scan');
        lastOrphanScanResult = result;
        
        // Hide initial content, show results
        contentDiv.style.display = 'none';
        resultsDiv.style.display = 'block';
        
        // Build summary
        const summaryDiv = document.getElementById('orphanSummary');
        const hasOrphans = result.total_count > 0;
        
        // Handle new orphan types (may be undefined in older API responses)
        const orphanProjects = result.orphan_projects || [];
        const mismatchedMessages = result.mismatched_messages || [];
        const mismatchedParts = result.mismatched_parts || [];
        const staleCacheSessions = result.stale_cache_sessions || [];
        
        summaryDiv.innerHTML = `
            <h4>Scan Results</h4>
            <div class="stat">
                <span class="label">Orphaned projects (no sessions):</span>
                <span class="value ${orphanProjects.length > 0 ? 'warning' : 'success'}">${orphanProjects.length}</span>
            </div>
            <div class="stat">
                <span class="label">Orphaned session_diffs:</span>
                <span class="value ${result.session_diffs.length > 0 ? 'warning' : 'success'}">${result.session_diffs.length}</span>
            </div>
            <div class="stat">
                <span class="label">Orphaned todos:</span>
                <span class="value ${result.todos.length > 0 ? 'warning' : 'success'}">${result.todos.length}</span>
            </div>
            <div class="stat">
                <span class="label">Orphaned message directories:</span>
                <span class="value ${result.messages.length > 0 ? 'warning' : 'success'}">${result.messages.length}</span>
            </div>
            <div class="stat">
                <span class="label">Orphaned part directories:</span>
                <span class="value ${result.parts.length > 0 ? 'warning' : 'success'}">${result.parts.length}</span>
            </div>
            <div class="stat">
                <span class="label">Mismatched message files:</span>
                <span class="value ${mismatchedMessages.length > 0 ? 'warning' : 'success'}">${mismatchedMessages.length}</span>
            </div>
            <div class="stat">
                <span class="label">Mismatched part files:</span>
                <span class="value ${mismatchedParts.length > 0 ? 'warning' : 'success'}">${mismatchedParts.length}</span>
            </div>
            <div class="stat">
                <span class="label">Stale Desktop cache sessions:</span>
                <span class="value ${staleCacheSessions.length > 0 ? 'warning' : 'success'}">${staleCacheSessions.length}</span>
            </div>
            <div class="stat" style="margin-top: 10px; padding-top: 10px; border-top: 2px solid #0f3460;">
                <span class="label"><strong>Total orphans:</strong></span>
                <span class="value ${hasOrphans ? 'warning' : 'success'}"><strong>${result.total_count}</strong></span>
            </div>
            <div class="stat">
                <span class="label"><strong>Total size:</strong></span>
                <span class="value ${hasOrphans ? 'warning' : 'success'}"><strong>${formatBytes(result.total_size)}</strong></span>
            </div>
        `;
        
        // Build details
        const detailsDiv = document.getElementById('orphanDetails');
        if (hasOrphans) {
            let detailsHtml = '<h4>Orphan Details</h4>';
            
            // Show orphan projects first
            orphanProjects.forEach(item => {
                detailsHtml += `<div class="orphan-item"><span class="type" style="color:#e74c3c;">orphan project:</span> <span class="id">${escapeHtml(item.name)}</span><br><small style="color:#888;">worktree: ${escapeHtml(item.worktree)}</small></div>`;
            });
            
            result.session_diffs.forEach(item => {
                detailsHtml += `<div class="orphan-item"><span class="type">session_diff:</span> <span class="id">${item.session_id}</span></div>`;
            });
            result.todos.forEach(item => {
                detailsHtml += `<div class="orphan-item"><span class="type">todo:</span> <span class="id">${item.session_id}</span></div>`;
            });
            result.messages.forEach(item => {
                detailsHtml += `<div class="orphan-item"><span class="type">messages (${item.file_count} files):</span> <span class="id">${item.session_id}</span></div>`;
            });
            result.parts.forEach(item => {
                detailsHtml += `<div class="orphan-item"><span class="type">parts (${item.file_count} files):</span> <span class="id">${item.message_id}</span></div>`;
            });
            
            // New: show mismatched message files
            mismatchedMessages.forEach(item => {
                detailsHtml += `<div class="orphan-item"><span class="type" style="color:#e67e22;">mismatched msg:</span> <span class="id">${item.message_id}</span><br><small style="color:#888;">${escapeHtml(item.issue)}</small></div>`;
            });
            
            // New: show mismatched part files
            mismatchedParts.forEach(item => {
                const issueText = item.issues ? item.issues.join('; ') : 'reference mismatch';
                detailsHtml += `<div class="orphan-item"><span class="type" style="color:#e67e22;">mismatched part:</span> <span class="id">${item.part_id}</span><br><small style="color:#888;">${escapeHtml(issueText)}</small></div>`;
            });
            
            // Show stale Desktop cache sessions
            staleCacheSessions.forEach(item => {
                detailsHtml += `<div class="orphan-item"><span class="type" style="color:#9b59b6;">stale cache:</span> <span class="id">${item.session_id}</span><br><small style="color:#888;">Session no longer exists on disk</small></div>`;
            });
            
            detailsDiv.innerHTML = detailsHtml;
            detailsDiv.style.display = 'block';
            cleanupBtn.style.display = 'inline-block';
        } else {
            detailsDiv.innerHTML = '<p style="color: #2ecc71; text-align: center;">No orphaned data found. Your storage is clean!</p>';
            detailsDiv.style.display = 'block';
            cleanupBtn.style.display = 'none';
        }
        
        startBtn.textContent = 'Scan Again';
        startBtn.disabled = false;
        document.getElementById('scanOrphansTitle').textContent = 'Scan Results';
        
    } catch (e) {
        contentDiv.innerHTML = `<p style="color: #e74c3c;">Error during scan: ${escapeHtml(e.message)}</p>`;
        contentDiv.style.display = 'block';
        startBtn.textContent = 'Retry Scan';
        startBtn.disabled = false;
    }
}

async function cleanupOrphans() {
    if (!lastOrphanScanResult || lastOrphanScanResult.total_count === 0) {
        alert('No orphans to clean up. Please run a scan first.');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete ${lastOrphanScanResult.total_count} orphaned items (${formatBytes(lastOrphanScanResult.total_size)})?\n\nThis action cannot be undone.`)) {
        return;
    }
    
    const cleanupBtn = document.getElementById('cleanupOrphansBtn');
    cleanupBtn.disabled = true;
    cleanupBtn.textContent = 'Cleaning...';
    
    try {
        const result = await api('/orphans/cleanup', { method: 'POST' });
        
        const totalDeleted = result.deleted.session_diffs + result.deleted.todos + result.deleted.messages + result.deleted.parts;
        
        let message = `Cleanup complete!\n\nDeleted:\n`;
        message += `- ${result.deleted.session_diffs} session_diff files\n`;
        message += `- ${result.deleted.todos} todo files\n`;
        message += `- ${result.deleted.messages} message directories\n`;
        message += `- ${result.deleted.parts} part directories\n`;
        message += `\nTotal space freed: ${formatBytes(result.deleted.total_size_freed)}`;
        
        if (result.errors.length > 0) {
            message += `\n\n${result.errors.length} errors occurred during cleanup.`;
        }
        
        alert(message);
        
        // Re-run scan to show updated state
        lastOrphanScanResult = null;
        cleanupBtn.style.display = 'none';
        document.getElementById('scanOrphansContent').style.display = 'block';
        document.getElementById('scanOrphansContent').innerHTML = '<p class="warning-text">Cleanup complete. Click "Scan Again" to verify.</p>';
        document.getElementById('scanOrphansResults').style.display = 'none';
        document.getElementById('startScanBtn').textContent = 'Scan Again';
        
    } catch (e) {
        alert('Error during cleanup: ' + e.message);
    } finally {
        cleanupBtn.disabled = false;
        cleanupBtn.textContent = 'Delete Orphans';
    }
}

// =============================================================================
// Git Config Modal Functions
// =============================================================================

function showGitConfigModal() {
    document.getElementById('gitConfigName').value = '';
    document.getElementById('gitConfigEmail').value = '';
    document.getElementById('gitConfigModal').classList.add('active');
    document.getElementById('gitConfigName').focus();
}

function closeGitConfigModal() {
    document.getElementById('gitConfigModal').classList.remove('active');
    pendingGitConfigOperation = null;
}

function cancelGitConfig() {
    closeGitConfigModal();
}

async function confirmGitConfig() {
    const name = document.getElementById('gitConfigName').value.trim();
    const email = document.getElementById('gitConfigEmail').value.trim();
    
    if (!name) {
        alert('Please enter your name');
        return;
    }
    if (!email) {
        alert('Please enter your email');
        return;
    }
    
    // Simple email validation
    if (!email.includes('@') || !email.includes('.')) {
        alert('Please enter a valid email address');
        return;
    }
    
    const operation = pendingGitConfigOperation;
    closeGitConfigModal();
    
    if (!operation) return;
    
    // Retry the original operation with git config
    switch (operation.type) {
        case 'create_project':
            await confirmAddProject(name, email);
            break;
        case 'update_project':
            await confirmEdit(name, email);
            break;
        case 'repair_project':
            await checkRepairProject(name, email);
            break;
    }
}

// Add keyboard handler for git config modal
document.addEventListener('keydown', (e) => {
    if (document.getElementById('gitConfigModal').classList.contains('active')) {
        if (e.key === 'Escape') cancelGitConfig();
        if (e.key === 'Enter') confirmGitConfig();
    }
});
