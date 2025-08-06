document.addEventListener('DOMContentLoaded', () => {
    // --- STATE AND HEADERS ---
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }
    const headers = { 'Authorization': `Bearer ${token}` };
    let currentSquads = [];
    let ALL_ROLES = {};
    let EMOJI_MAP = {};
    let SQUAD_TEMPLATES = [];
    let lockInterval = null;
    let currentUser = null;
    let isPageInitialized = false;
    let fullRoster = [];

    // --- ELEMENT SELECTORS ---
    const eventDropdown = document.getElementById('event-dropdown');
    const rosterAndBuildSection = document.getElementById('roster-and-build');
    const rosterList = document.getElementById('roster-list');
    const buildForm = document.getElementById('build-form');
    const buildBtn = document.getElementById('build-btn');
    const workshopSection = document.getElementById('workshop-section');
    const workshopArea = document.getElementById('workshop-area');
    const channelDropdown = document.getElementById('channel-dropdown');
    const sendBtn = document.getElementById('send-btn');
    const refreshRosterBtn = document.getElementById('refresh-roster-btn');
    const adminLink = document.getElementById('admin-link');
    const logoutBtn = document.getElementById('logout-btn');
    const lockOverlay = document.getElementById('lock-overlay');
    const lockMessage = document.getElementById('lock-message');
    const mainContent = document.getElementById('main-content');
    const clearLockBtn = document.getElementById('clear-lock-btn');
    const templateDropdown = document.getElementById('template-dropdown');

    // Modals
    const editModal = document.getElementById('edit-member-modal');
    const editMemberForm = document.getElementById('edit-member-form');
    const modalMemberName = document.getElementById('modal-member-name');
    const modalMemberIdInput = document.getElementById('modal-member-id');
    const modalRoleSelect = document.getElementById('modal-role-select');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const assignTaskModal = document.getElementById('assign-task-modal');
    const assignTaskForm = document.getElementById('assign-task-form');
    const taskModalMemberName = document.getElementById('task-modal-member-name');
    const taskModalMemberIdInput = document.getElementById('task-modal-member-id');
    const modalTaskSelect = document.getElementById('modal-task-select');
    const taskModalCancelBtn = document.getElementById('task-modal-cancel-btn');
    const promoteModal = document.getElementById('promote-tentative-modal');
    const promoteForm = document.getElementById('promote-tentative-form');
    const promoteModalMemberName = document.getElementById('promote-modal-member-name');
    const promoteModalMemberId = document.getElementById('promote-modal-member-id');
    const promoteModalRoleSelect = document.getElementById('promote-modal-role-select');
    const promoteModalCancelBtn = document.getElementById('promote-modal-cancel-btn');

    const STARTUP_TASKS = [
        "HQ1 Supplies", "HQ1 Nodes Engineer", "HQ2 Supplies", "HQ2 Nodes Engineer",
        "HQ3 Supplies", "HQ3 Nodes Engineer", "HQ1 Driver (Transport)", "HQ1 Driver (Supplies)",
        "HQ2 Driver (Transport)", "HQ2 Driver (Supplies)", "HQ3 Driver (Transport)", "HQ3 Driver (Supplies)",
        "Top Left Garrison", "Top Middle Garrison", "Top Right Garrison",
        "Bottom Left Garrison", "Bottom Middle Garrison", "Bottom Right Garrison"
    ];

    const handleApiError = async (response) => {
        if (response.ok) return false;
        if (response.status === 401) {
            localStorage.removeItem('accessToken');
            window.location.href = '/login';
            return true;
        }
        if (response.status === 423) return false;
        const errorData = await response.json().catch(() => ({ detail: 'An unknown error occurred.' }));
        alert(`An error occurred: ${errorData.detail}`);
        return true;
    };

    const createEmojiHtml = (emojiString) => {
        if (!emojiString) return '<span>❔</span>';
        const match = emojiString.match(/<a?:.*?:(\d+?)>/);
        if (match) {
            const url = `https://cdn.discordapp.com/emojis/${match[1]}.${emojiString.startsWith('<a:') ? 'gif' : 'png'}`;
            return `<img src="${url}" alt="emoji" class="w-6 h-6 inline-block">`;
        }
        return `<span class="text-xl">${emojiString}</span>`;
    };

    const setLockedState = (isLocked, message = '') => {
        if (isLocked) {
            lockMessage.textContent = message;
            lockOverlay.classList.remove('hidden');
            mainContent.classList.add('pointer-events-none', 'opacity-50');
        } else {
            lockOverlay.classList.add('hidden');
            mainContent.classList.remove('pointer-events-none', 'opacity-50');
        }
    };

    const acquireLock = async (eventId) => {
        if (!currentUser) return false;
        try {
            const response = await fetch(`/api/events/${eventId}/lock`, { method: 'POST', headers });
            if (response.status === 423) {
                const lockStatus = await (await fetch(`/api/events/${eventId}/lock-status`, { headers })).json();
                if (lockStatus.is_locked && lockStatus.locked_by_user_id !== currentUser.id) {
                    setLockedState(true, `This event is locked by: ${lockStatus.locked_by_username}. Read-only mode.`);
                } else {
                    setLockedState(false);
                }
                return false;
            }
            if (await handleApiError(response)) return false;
            setLockedState(false);
            if (lockInterval) clearInterval(lockInterval);
            lockInterval = setInterval(() => { fetch(`/api/events/${eventId}/lock`, { method: 'POST', headers }); }, 60000);
            return true;
        } catch (error) {
            console.error("Error in acquireLock:", error);
            return false;
        }
    };

    const releaseLock = async (eventId) => {
        if (lockInterval) clearInterval(lockInterval);
        lockInterval = null;
        if (eventId) await fetch(`/api/events/${eventId}/unlock`, { method: 'POST', headers, keepalive: true }).catch(() => {});
    };

    window.addEventListener('beforeunload', () => releaseLock(eventDropdown.value));

    // --- Template and Form Logic ---
    const populateTemplateDropdown = () => {
        templateDropdown.innerHTML = '<option value="">-- Manual Build --</option>';
        SQUAD_TEMPLATES.forEach(template => {
            templateDropdown.add(new Option(template.template_name, template.template_id));
        });
    };

    const generateBuildForm = (templateId) => {
        buildForm.innerHTML = '';
        const template = SQUAD_TEMPLATES.find(t => t.template_id == templateId);
        if (!template) {
            buildForm.innerHTML = `
                <div>
                    <label for="squad_count_Commander" class="block text-sm font-medium">Commander</label>
                    <input type="number" id="squad_count_Commander" name="Commander" value="1" min="0" required class="mt-1 w-full bg-gray-700 border-gray-600 rounded-md p-2">
                </div>
            `;
            return;
        }

        template.definitions.forEach(def => {
            const div = document.createElement('div');
            div.innerHTML = `
                <label for="squad_count_${def.squad_name}" class="block text-sm font-medium">${def.squad_name}</label>
                <input type="number" id="squad_count_${def.squad_name}" name="${def.squad_name}" value="${def.default_count}" min="0" required class="mt-1 w-full bg-gray-700 border-gray-600 rounded-md p-2">
            `;
            buildForm.appendChild(div);
        });
        
        if (!buildForm.querySelector('#squad_count_Commander')) {
             const div = document.createElement('div');
             div.innerHTML = `
                <label for="squad_count_Commander" class="block text-sm font-medium">Commander</label>
                <input type="number" id="squad_count_Commander" name="Commander" value="1" min="0" required class="mt-1 w-full bg-gray-700 border-gray-600 rounded-md p-2">
            `;
            buildForm.prepend(div);
        }
    };

    templateDropdown.addEventListener('change', () => generateBuildForm(templateDropdown.value));

    buildBtn.addEventListener('click', async () => {
        const eventId = eventDropdown.value;
        const templateId = templateDropdown.value;
        if (!eventId || !templateId) {
            alert('Please select an event and a squad template.');
            return;
        }

        const formData = new FormData(buildForm);
        const squadCounts = {};
        for (let [key, value] of formData.entries()) {
            squadCounts[key] = parseInt(value, 10) || 0;
        }
        
        const buildRequest = { squad_counts: squadCounts, template_id: parseInt(templateId) };

        buildBtn.textContent = 'Building...';
        buildBtn.disabled = true;
        try {
            const response = await fetch(`/api/events/${eventId}/build-squads`, {
                method: 'POST',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify(buildRequest)
            });
            if (await handleApiError(response)) return;
            renderWorkshop(await response.json());
        } catch (error) {
            alert('Error building squads.');
        } finally {
            buildBtn.textContent = 'Re-Build Squads';
            buildBtn.disabled = false;
        }
    });

    // --- Other Event Listeners ---
    refreshRosterBtn.addEventListener('click', async () => {
        const eventId = eventDropdown.value;
        if (!eventId || currentSquads.length === 0) return;
        refreshRosterBtn.textContent = 'Refreshing...';
        refreshRosterBtn.disabled = true;
        try {
            const response = await fetch(`/api/events/${eventId}/refresh-roster`, {
                method: 'POST',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ squads: currentSquads })
            });
            if (await handleApiError(response)) return;
            await fetchAndDisplayRoster(eventId);
            renderWorkshop(await response.json());
            alert('Roster has been updated!');
        } catch (error) {
            alert('Error refreshing roster.');
        } finally {
            refreshRosterBtn.textContent = 'Refresh Roster';
            refreshRosterBtn.disabled = false;
        }
    });

    clearLockBtn.addEventListener('click', async () => {
        await releaseLock(eventDropdown.value);
        setLockedState(false);
        eventDropdown.value = '';
        rosterAndBuildSection.classList.add('hidden');
        workshopSection.classList.add('hidden');
    });

    logoutBtn.addEventListener('click', () => {
        releaseLock(eventDropdown.value);
        localStorage.removeItem('accessToken');
        window.location.href = '/login';
    });
    
    sendBtn.addEventListener('click', async () => {
        const selectedChannelId = channelDropdown.value;
        const eventId = eventDropdown.value;
        
        if (!selectedChannelId || currentSquads.length === 0 || !eventId) {
            alert('Please select an event and channel, and build squads first.');
            return;
        }
        
        sendBtn.textContent = 'Sending...';
        sendBtn.disabled = true;
        
        try {
            const url = `/api/events/send-embed?event_id=${eventId}`;
            const mentionAttendees = document.getElementById('mention-attendees-checkbox').checked;

            const response = await fetch(url, {
                method: 'POST',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: selectedChannelId,
                    squads: currentSquads,
                    mention_accepted: mentionAttendees
                })
            });
            
            if (await handleApiError(response)) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            
            alert('Squad embed sent successfully!');
            await releaseLock(eventId);
            setLockedState(true, 'Squads sent. This event is now read-only.');

        } catch (error) {
            console.error("Error in sendBtn listener:", error.message);
        } finally {
            sendBtn.textContent = 'Send to Discord Channel';
            sendBtn.disabled = false;
        }
    });

    document.body.addEventListener('click', (e) => {
        const editBtn = e.target.closest('.edit-member-btn');
        const taskBtn = e.target.closest('.assign-task-btn');
        const promoteBtn = e.target.closest('.promote-tentative-btn');

        if (editBtn) {
            const memberItem = editBtn.closest('.member-item');
            modalMemberName.textContent = memberItem.querySelector('.member-name').textContent;
            modalMemberIdInput.value = memberItem.dataset.memberId;
            const currentRole = memberItem.querySelector('.assigned-role-text').textContent;
            modalRoleSelect.innerHTML = '';
            const allRoles = [...new Set([...ALL_ROLES.roles, ...Object.values(ALL_ROLES.subclasses).flat()])].sort();
            allRoles.forEach(role => {
                const option = new Option(role, role);
                if (role === currentRole) option.selected = true;
                modalRoleSelect.add(option);
            });
            editModal.classList.remove('hidden');
        } else if (taskBtn) {
            const memberItem = taskBtn.closest('.member-item');
            taskModalMemberName.textContent = memberItem.querySelector('.member-name').textContent;
            taskModalMemberIdInput.value = memberItem.dataset.memberId;
            modalTaskSelect.innerHTML = '<option value="">-- None --</option>';
            STARTUP_TASKS.forEach(task => modalTaskSelect.add(new Option(task, task)));
            modalTaskSelect.value = memberItem.querySelector('.startup-task-text')?.textContent || "";
            assignTaskModal.classList.remove('hidden');
        } else if (promoteBtn) {
            const memberItem = promoteBtn.closest('.tentative-member-item');
            promoteModalMemberName.textContent = memberItem.dataset.displayName;
            promoteModalMemberId.value = memberItem.dataset.userId;
            promoteModalRoleSelect.innerHTML = '';
            const allRoles = [...new Set([...ALL_ROLES.roles, ...Object.values(ALL_ROLES.subclasses).flat()])].sort();
            allRoles.forEach(role => promoteModalRoleSelect.add(new Option(role, role)));
            promoteModal.classList.remove('hidden');
        }
    });

    promoteModalCancelBtn.addEventListener('click', () => promoteModal.classList.add('hidden'));
    
    // --- START OF CHANGE ---
    promoteForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const eventId = eventDropdown.value;
        const userId = promoteModalMemberId.value;
        const newRoleName = promoteModalRoleSelect.value;
        const playerName = promoteModalMemberName.textContent;

        try {
            const response = await fetch(`/api/events/${eventId}/promote-tentative`, {
                method: 'POST',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: parseInt(userId), new_role_name: newRoleName })
            });

            if (await handleApiError(response)) return;
            
            const updatedSquads = await response.json();

            // Re-fetch the roster and re-render everything to ensure consistency
            await fetchAndDisplayRoster(eventId);
            renderWorkshop(updatedSquads);
            
            promoteModal.classList.add('hidden');
            alert(`${playerName} promoted. The Discord embed will update on its next cycle.`);

        } catch (err) {
            alert("Error: Could not promote player.");
            console.error(err);
        }
    });
    // --- END OF CHANGE ---

    modalCancelBtn.addEventListener('click', () => editModal.classList.add('hidden'));
    taskModalCancelBtn.addEventListener('click', () => assignTaskModal.classList.add('hidden'));

    assignTaskForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const memberId = taskModalMemberIdInput.value;
        const task = modalTaskSelect.value;
        try {
            const response = await fetch(`/api/squads/members/${memberId}/task`, {
                method: 'PUT',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ task: task })
            });
            if (await handleApiError(response)) return;
            const memberEl = document.querySelector(`[data-member-id='${memberId}']`);
            if (memberEl) {
                let taskTextEl = memberEl.querySelector('.startup-task-text');
                if (!taskTextEl && task) {
                    taskTextEl = document.createElement('div');
                    taskTextEl.className = 'text-xs text-yellow-400 font-semibold startup-task-text mt-1';
                    memberEl.querySelector('.member-info').appendChild(taskTextEl);
                }
                if (taskTextEl) taskTextEl.textContent = task;
                if (!task && taskTextEl) taskTextEl.remove();
            }
            assignTaskModal.classList.add('hidden');
        } catch (err) { alert("Error: Could not update task."); }
    });

    editMemberForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const memberId = modalMemberIdInput.value;
        const newRole = modalRoleSelect.value;
        const eventId = eventDropdown.value;
        try {
            const response = await fetch(`/api/squads/members/${memberId}/role`, {
                method: 'PUT',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_role_name: newRole, event_id: parseInt(eventId) })
            });
            if (await handleApiError(response)) return;
            const memberEl = document.querySelector(`[data-member-id='${memberId}']`);
            if (memberEl) {
                memberEl.querySelector('.member-emoji').innerHTML = createEmojiHtml(EMOJI_MAP[newRole]);
                memberEl.querySelector('.assigned-role-text').textContent = newRole;
            }
            editModal.classList.add('hidden');
            await fetchAndDisplayRoster(eventId);
        } catch (err) { alert("Error: Could not update role."); }
    });

    // --- Initial Page Load ---
    Promise.all([
        fetch('/api/users/me', { headers }),
        fetch('/api/squads/roles', { headers }),
        fetch('/api/events', { headers }),
        fetch('/api/squads/emojis', { headers }),
        fetch('/api/templates', { headers: { 'Authorization': `Bearer ${token}` } })
    ]).then(async ([userRes, rolesRes, eventsRes, emojiRes, templatesRes]) => {
        if (await handleApiError(userRes) || await handleApiError(rolesRes) || await handleApiError(eventsRes) || await handleApiError(emojiRes) || await handleApiError(templatesRes)) return;
        
        currentUser = await userRes.json();
        if (currentUser?.is_admin) adminLink.classList.remove('hidden');

        ALL_ROLES = await rolesRes.json();
        EMOJI_MAP = await emojiRes.json();
        SQUAD_TEMPLATES = await templatesRes.json();
        const events = await eventsRes.json();

        eventDropdown.innerHTML = '<option value="">-- Select an Event --</option>';
        events.forEach(event => eventDropdown.add(new Option(`${event.title} (${new Date(event.event_time).toLocaleString()})`, event.event_id)));
        
        populateTemplateDropdown();
        generateBuildForm(null);

        eventDropdown.addEventListener('change', handleEventSelection);
        isPageInitialized = true;

    }).catch(err => console.error("FATAL: Initial page data failed to load:", err));

    async function handleEventSelection() {
        if (!isPageInitialized || !currentUser) return;
        await releaseLock(eventDropdown.dataset.previousEventId);
        setLockedState(false);
        workshopSection.classList.add('hidden');
        rosterAndBuildSection.classList.add('hidden');
        const eventId = eventDropdown.value;
        eventDropdown.dataset.previousEventId = eventId;
        if (!eventId) return;
        await acquireLock(eventId);
        try {
            await fetchAndDisplayRoster(eventId);
            rosterAndBuildSection.classList.remove('hidden');
            const squadsResponse = await fetch(`/api/events/${eventId}/squads`, { headers });
            if(await handleApiError(squadsResponse)) return;
            const existingSquads = await squadsResponse.json();
            if (existingSquads?.length > 0) {
                buildBtn.textContent = 'Re-Build Squads';
                renderWorkshop(existingSquads);
            } else {
                buildBtn.textContent = 'Build Squads';
            }
        } catch (error) { console.error(`Error loading event data for ${eventId}:`, error); }
    }
    
    async function fetchAndDisplayRoster(eventId) {
        try {
            const rosterResponse = await fetch(`/api/events/${eventId}/signups`, { headers });
            if(await handleApiError(rosterResponse)) return;
            fullRoster = await rosterResponse.json();
            displayRoster(fullRoster);
        } catch (error) {
            console.error(`Error fetching roster for event ${eventId}:`, error);
            rosterList.innerHTML = '<p class="text-red-400">Could not load roster.</p>';
        }
    }

    function displayRoster(roster) {
        rosterList.innerHTML = '';
        const accepted = roster.filter(p => p.rsvp_status === 'Accepted');
        accepted.forEach(player => {
            const div = document.createElement('div');
            div.className = 'p-2 bg-gray-700 rounded-md text-sm flex items-center';
            const emojiKey = player.subclass_name || player.role_name;
            const emojiHtml = createEmojiHtml(EMOJI_MAP[emojiKey]);
            div.innerHTML = `<span class="flex-shrink-0 w-6 h-6 flex items-center justify-center">${emojiHtml}</span><span class="ml-2">${player.display_name}</span>`;
            rosterList.appendChild(div);
        });
        renderTentativePlayers();
    }

    function renderTentativePlayers() {
        let tentativeBox = document.getElementById('tentative-players-box');
        if (!tentativeBox) {
            tentativeBox = document.createElement('div');
            tentativeBox.id = 'tentative-players-box';
            tentativeBox.className = 'bg-gray-700 p-4 rounded-lg';
            workshopArea.appendChild(tentativeBox);
        }
        const tentative = fullRoster.filter(p => p.rsvp_status === 'Tentative');
        tentativeBox.innerHTML = `<h3 class="font-bold text-white border-b border-gray-600 pb-2 mb-2">Tentative Players (${tentative.length})</h3>`;
        const memberList = document.createElement('div');
        memberList.className = 'space-y-1';
        tentative.forEach(player => {
            const memberEl = document.createElement('div');
            memberEl.className = 'p-2 bg-gray-800 rounded-md flex justify-between items-center tentative-member-item';
            memberEl.dataset.userId = player.user_id;
            memberEl.dataset.displayName = player.display_name;
            memberEl.innerHTML = `
                <div class="flex items-center"><span class="mr-2">🤔</span><span>${player.display_name}</span></div>
                <button class="promote-tentative-btn text-green-400 hover:text-green-600" title="Promote to Accepted">▲</button>
            `;
            memberList.appendChild(memberEl);
        });
        tentativeBox.appendChild(memberList);
    }

    async function loadChannels() {
        try {
            const response = await fetch('/api/events/channels', { headers });
            if (await handleApiError(response)) return;
            const channels = await response.json();
            channelDropdown.innerHTML = '<option value="">-- Select a Channel or Thread --</option>';
            let currentCategory = null;
            let optgroup = null;
            channels.forEach(channel => {
                if (channel.category !== currentCategory) {
                    currentCategory = channel.category;
                    optgroup = currentCategory ? document.createElement('optgroup') : null;
                    if (optgroup) {
                        optgroup.label = currentCategory;
                        channelDropdown.appendChild(optgroup);
                    }
                }
                (optgroup || channelDropdown).appendChild(new Option(channel.name, channel.id));
            });
        } catch(err) { console.error("Could not load channels", err)}
    }

    function renderWorkshop(squads) {
        currentSquads = squads;
        workshopArea.innerHTML = '';
        (squads || []).forEach(squad => {
            const squadBox = document.createElement('div');
            squadBox.className = 'bg-gray-700 p-4 rounded-lg';
            squadBox.innerHTML = `<h3 class="font-bold text-white border-b border-gray-600 pb-2 mb-2">${squad.name}</h3>`;
            const memberList = document.createElement('div');
            memberList.className = 'member-list space-y-1 min-h-[40px] p-2 rounded-lg';
            memberList.dataset.squadId = squad.squad_id;
            (squad.members || []).forEach(member => {
                const memberEl = document.createElement('div');
                memberEl.className = 'p-2 bg-gray-800 rounded-md flex justify-between items-center member-item cursor-grab';
                memberEl.dataset.memberId = member.squad_member_id;
                const emojiHtml = createEmojiHtml(EMOJI_MAP[member.assigned_role_name]);
                memberEl.innerHTML = `
                    <div class="member-info flex-grow">
                        <div class="flex items-center">
                            <span class="member-emoji mr-2 flex-shrink-0 w-6 h-6 flex items-center justify-center">${emojiHtml}</span>
                            <span class="member-name">${member.display_name}</span>
                            <span class="assigned-role-text hidden">${member.assigned_role_name}</span>
                        </div>
                        ${member.startup_task ? `<div class="text-xs text-yellow-400 font-semibold startup-task-text mt-1">${member.startup_task}</div>` : ''}
                    </div>
                    <div class="flex items-center space-x-2">
                        <button class="assign-task-btn text-gray-400 hover:text-white" title="Assign Task">📋</button>
                        <button class="edit-member-btn text-gray-400 hover:text-white" title="Edit Role">⚙️</button>
                    </div>`;
                memberList.appendChild(memberEl);
            });
            squadBox.appendChild(memberList);
            workshopArea.appendChild(squadBox);
        });
        renderTentativePlayers();
        document.querySelectorAll('.member-list').forEach(list => {
            new Sortable(list, { 
                group: 'squads', 
                animation: 150, 
                onEnd: async (evt) => {
                    const memberId = evt.item.dataset.memberId;
                    const newSquadId = evt.to.dataset.squadId;
                    try {
                        const response = await fetch(`/api/squads/members/${memberId}/move`, {
                            method: 'PUT', headers: { ...headers, 'Content-Type': 'application/json' },
                            body: JSON.stringify({ new_squad_id: parseInt(newSquadId) })
                        });
                        if (await handleApiError(response)) throw new Error('Move failed on server');
                    } catch (err) {
                        console.error("Drag-and-drop error:", err);
                        alert("Error: Could not move member. " + err.message);
                    }
                }
            });
        });
        workshopSection.classList.remove('hidden');
        loadChannels();
    }
});
