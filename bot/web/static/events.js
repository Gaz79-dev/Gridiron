document.addEventListener('DOMContentLoaded', () => {
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }
    const headers = { 
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };

    const CURATED_TIMEZONES = {
        "USA / Canada": [
            "US/Pacific", "US/Mountain", "US/Central", "US/Eastern",
            "Canada/Atlantic", "US/Alaska", "US/Hawaii"
        ],
        "UK / Europe": [
            "Europe/London", "Europe/Paris", "Europe/Berlin", 
            "Europe/Helsinki", "Europe/Moscow"
        ],
        "Other": ["UTC"]
    };

    let gameSystems = [];
    let squadTemplates = [];
    let discordChannels = [];
    let discordRoles = [];

    // Discord IDs are snowflakes and are larger than JavaScript's safe integer limit.
    // Keep them as strings in the browser and let the Python API parse them safely.
    const getSelectedRoleIds = (selectId) => {
        const select = document.getElementById(selectId);
        if (!select) return [];
        return Array.from(select.selectedOptions).map(option => option.value).filter(value => /^\d+$/.test(value));
    };

    const setSelectedRoleIds = (selectId, selectedRoleIds = []) => {
        const select = document.getElementById(selectId);
        if (!select) return;
        const selected = new Set((selectedRoleIds || []).map(String));
        Array.from(select.options).forEach(option => {
            option.selected = selected.has(String(option.value));
        });
    };

    const DEFAULT_RECREATION_HOURS = {
        daily: 24,
        weekly: 168,
        monthly: 720,
    };

    const getRecurrenceSettings = (prefix) => {
        const recurrenceRule = document.getElementById(`${prefix}-recurrence-rule`)?.value || 'none';
        const isRecurring = recurrenceRule !== 'none';
        const hoursInput = document.getElementById(`${prefix}-recreation-hours`);
        const parsedHours = parseInt(hoursInput?.value || '', 10);
        const recreationHours = Number.isFinite(parsedHours) && parsedHours > 0
            ? parsedHours
            : (DEFAULT_RECREATION_HOURS[recurrenceRule] || 168);

        return {
            is_recurring: isRecurring,
            recurrence_rule: isRecurring ? recurrenceRule : null,
            recreation_hours: isRecurring ? recreationHours : null,
        };
    };

    const syncRecurrenceControls = (prefix) => {
        const ruleSelect = document.getElementById(`${prefix}-recurrence-rule`);
        const hoursInput = document.getElementById(`${prefix}-recreation-hours`);
        if (!ruleSelect || !hoursInput) return;

        const isRecurring = ruleSelect.value !== 'none';
        hoursInput.disabled = !isRecurring;
        hoursInput.classList.toggle('opacity-50', !isRecurring);

        if (isRecurring && (!hoursInput.value || parseInt(hoursInput.value, 10) <= 0)) {
            hoursInput.value = DEFAULT_RECREATION_HOURS[ruleSelect.value] || 168;
        }
    };

    const populateTimezoneSelect = (selectId) => {
        const select = document.getElementById(selectId);
        if (!select) return;
        select.innerHTML = '';
        for (const region in CURATED_TIMEZONES) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = region;
            CURATED_TIMEZONES[region].forEach(tz => {
                const option = document.createElement('option');
                option.value = tz;
                option.textContent = tz;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        }
        if ([...select.options].some(o => o.value === 'Europe/London')) select.value = 'Europe/London';
    };

    const populateChannelSelect = (selectId) => {
        const select = document.getElementById(selectId);
        if (!select) return;
        select.innerHTML = '<option value="">-- Select a Channel --</option>';
        let currentCategory = null;
        let optgroup = null;
        discordChannels.forEach(channel => {
            if (channel.category !== currentCategory) {
                currentCategory = channel.category;
                optgroup = currentCategory ? document.createElement('optgroup') : null;
                if (optgroup) {
                    optgroup.label = currentCategory;
                    select.appendChild(optgroup);
                }
            }
            (optgroup || select).appendChild(new Option(channel.name, channel.id));
        });
    };

    const populateRoleMultiSelect = (selectId, selectedRoleIds = []) => {
        const select = document.getElementById(selectId);
        if (!select) return;
        const selected = new Set((selectedRoleIds || []).map(String));
        select.innerHTML = '';

        if (!discordRoles.length) {
            const option = new Option('No Discord roles available', '');
            option.disabled = true;
            select.add(option);
            return;
        }

        discordRoles.forEach(role => {
            const option = new Option(role.name, role.id);
            option.selected = selected.has(String(role.id));
            select.add(option);
        });
    };

    const populateAllRoleMultiSelects = () => {
        populateRoleMultiSelect('create-mention-role-ids');
        populateRoleMultiSelect('create-restrict-role-ids');
        populateRoleMultiSelect('edit-mention-role-ids');
        populateRoleMultiSelect('edit-restrict-role-ids');
    };


    const populateGameSelect = () => {
        const gameSelect = document.getElementById('create-game-id');
        if (!gameSelect) return;
        gameSelect.innerHTML = gameSystems.map(game => `<option value="${game.game_id}">${game.display_name}</option>`).join('');
        populateTemplateSelect();
    };

    const populateTemplateSelect = () => {
        const gameSelect = document.getElementById('create-game-id');
        const templateSelect = document.getElementById('create-template-id');
        if (!gameSelect || !templateSelect) return;
        const selectedGame = gameSelect.value || 'hll';
        const templatesForGame = squadTemplates.filter(t => (t.game_id || 'hll') === selectedGame);
        templateSelect.innerHTML = '<option value="">-- No Template --</option>';
        templatesForGame.forEach(template => templateSelect.add(new Option(template.template_name, template.template_id)));
        if (templatesForGame.length) templateSelect.value = templatesForGame[0].template_id;
    };

    const populateEditGameSelect = (selectedGame = 'hll') => {
        const gameSelect = document.getElementById('edit-game-id');
        if (!gameSelect) return;
        gameSelect.innerHTML = gameSystems.map(game => `<option value="${game.game_id}">${game.display_name}</option>`).join('');
        gameSelect.value = selectedGame || 'hll';
        populateEditTemplateSelect(null);
    };

    const populateEditTemplateSelect = (selectedTemplateId = null) => {
        const gameSelect = document.getElementById('edit-game-id');
        const templateSelect = document.getElementById('edit-template-id');
        if (!gameSelect || !templateSelect) return;
        const selectedGame = gameSelect.value || 'hll';
        const templatesForGame = squadTemplates.filter(t => (t.game_id || 'hll') === selectedGame);
        templateSelect.innerHTML = '<option value="">-- No Template --</option>';
        templatesForGame.forEach(template => templateSelect.add(new Option(template.template_name, template.template_id)));
        if (selectedTemplateId) templateSelect.value = String(selectedTemplateId);
    };

    // --- Page sections and buttons ---
    // NEW: Add selectors for the upcoming events view
    const upcomingView = document.getElementById('upcoming-events-view');
    const recurringView = document.getElementById('recurring-events-view');
    const deletedView = document.getElementById('deleted-events-view');
    const viewUpcomingBtn = document.getElementById('view-upcoming-btn');
    const viewRecurringBtn = document.getElementById('view-recurring-btn');
    const viewDeletedBtn = document.getElementById('view-deleted-btn');
    const upcomingEventsBody = document.getElementById('upcoming-events-body');
    const recurringEventsBody = document.getElementById('recurring-events-body');
    const deletedEventsBody = document.getElementById('deleted-events-body');
    
    // --- Modal elements ---
    const modal = document.getElementById('edit-event-modal');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const editEventForm = document.getElementById('edit-event-form');
    const editEventIdInput = document.getElementById('edit-event-id');
    const createEventForm = document.getElementById('create-event-form');
    const createEventBtn = document.getElementById('create-event-btn');
    const createEventMessage = document.getElementById('create-event-message');
    const createGameSelect = document.getElementById('create-game-id');
    const editGameSelect = document.getElementById('edit-game-id');
    let editingEventIsRecurring = false;

    // --- VIEW TOGGLING ---
    // NEW: Add event listener for the upcoming events button and update all listeners
    viewUpcomingBtn.addEventListener('click', () => {
        upcomingView.classList.remove('hidden');
        recurringView.classList.add('hidden');
        deletedView.classList.add('hidden');
        viewUpcomingBtn.classList.replace('bg-gray-700', 'bg-blue-600');
        viewRecurringBtn.classList.replace('bg-blue-600', 'bg-gray-700');
        viewDeletedBtn.classList.replace('bg-blue-600', 'bg-gray-700');
    });

    viewRecurringBtn.addEventListener('click', () => {
        upcomingView.classList.add('hidden');
        recurringView.classList.remove('hidden');
        deletedView.classList.add('hidden');
        viewUpcomingBtn.classList.replace('bg-blue-600', 'bg-gray-700');
        viewRecurringBtn.classList.replace('bg-gray-700', 'bg-blue-600');
        viewDeletedBtn.classList.replace('bg-blue-600', 'bg-gray-700');
    });

    viewDeletedBtn.addEventListener('click', () => {
        upcomingView.classList.add('hidden');
        recurringView.classList.add('hidden');
        deletedView.classList.remove('hidden');
        viewUpcomingBtn.classList.replace('bg-blue-600', 'bg-gray-700');
        viewRecurringBtn.classList.replace('bg-blue-600', 'bg-gray-700');
        viewDeletedBtn.classList.replace('bg-gray-700', 'bg-blue-600');
    });

    // --- DATA LOADING ---
    // NEW: Function to load upcoming events
    const loadUpcomingEvents = async () => {
        try {
            const response = await fetch('/api/events', { headers });
            if (!response.ok) throw new Error('Failed to load upcoming events');
            const events = await response.json();
            
            upcomingEventsBody.innerHTML = '';
            events.forEach(event => {
                const tr = document.createElement('tr');
                tr.className = 'border-b border-gray-700';

                const eventTime = new Date(event.event_time);
                const endTime = event.end_time ? new Date(event.end_time) : new Date(eventTime.getTime() + 2 * 60 * 60 * 1000);
                const now = new Date();

                let statusText = '';
                let statusClass = '';
                if (now > endTime) {
                    statusText = 'Finished';
                    statusClass = 'bg-gray-700 text-gray-300';
                } else if (now >= eventTime && now <= endTime) {
                    statusText = 'Active';
                    statusClass = 'bg-green-900 text-green-300';
                } else {
                    statusText = 'Upcoming';
                    statusClass = 'bg-blue-900 text-blue-300';
                }

                tr.innerHTML = `
                    <td class="px-6 py-4">${event.title}</td>
                    <td class="px-6 py-4"><span class="text-xs uppercase bg-gray-700 text-gray-300 px-2 py-1 rounded">${event.game_id || 'hll'}</span></td>
                    <td class="px-6 py-4">${eventTime.toLocaleString()}</td>
                    <td class="px-6 py-4">
                        <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${statusClass}">
                            ${statusText}
                        </span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <button type="button" class="edit-btn inline-flex items-center rounded-md bg-blue-600 px-3 py-1 text-xs font-semibold text-white hover:bg-blue-700 mr-2" data-event-id="${event.event_id}">Edit</button>
                        <button type="button" class="delete-btn inline-flex items-center rounded-md bg-red-600 px-3 py-1 text-xs font-semibold text-white hover:bg-red-700" data-event-id="${event.event_id}">Delete</button>
                    </td>
                `;
                upcomingEventsBody.appendChild(tr);
            });
        } catch (error) {
            upcomingEventsBody.innerHTML = `<tr><td colspan="5" class="text-center p-4 text-red-400">${error.message}</td></tr>`;
        }
    };

    const loadRecurringEvents = async () => {
        try {
            const response = await fetch('/api/events/recurring', { headers });
            if (!response.ok) throw new Error('Failed to load recurring events');
            const events = await response.json();
            
            recurringEventsBody.innerHTML = '';
            events.forEach(event => {
                const tr = document.createElement('tr');
                tr.className = 'border-b border-gray-700';

                const nextEventTime = new Date(event.event_time).toLocaleString();
                const recurrence = event.recurrence_rule ? `${event.recurrence_rule.charAt(0).toUpperCase() + event.recurrence_rule.slice(1)}` : 'N/A';
                const lastCreated = event.last_recreated_at ? new Date(event.last_recreated_at).toLocaleString() : 'N/A';
                tr.innerHTML = `
                    <td class="px-6 py-4">${event.title}</td>
                    <td class="px-6 py-4">${nextEventTime}</td>
                    <td class="px-6 py-4">${recurrence}</td>
                    <td class="px-6 py-4">${lastCreated}</td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <button type="button" class="edit-btn inline-flex items-center rounded-md bg-blue-600 px-3 py-1 text-xs font-semibold text-white hover:bg-blue-700 mr-2" data-event-id="${event.event_id}">Edit</button>
                        <button type="button" class="delete-btn inline-flex items-center rounded-md bg-red-600 px-3 py-1 text-xs font-semibold text-white hover:bg-red-700" data-event-id="${event.event_id}">Delete</button>
                    </td>
                `;
                recurringEventsBody.appendChild(tr);
            });
        } catch (error) {
            recurringEventsBody.innerHTML = `<tr><td colspan="5" class="text-center p-4 text-red-400">${error.message}</td></tr>`;
        }
    };

    const loadDeletedEvents = async () => {
        try {
            const response = await fetch('/api/events/deleted', { headers });
            if (!response.ok) throw new Error('Failed to load deleted events');
            const events = await response.json();
            
            deletedEventsBody.innerHTML = '';
            events.forEach(event => {
                const tr = document.createElement('tr');
                tr.className = 'border-b border-gray-700';
                const eventTime = new Date(event.event_time).toLocaleString();
                const deletedAt = new Date(event.deleted_at).toLocaleString();

                tr.innerHTML = `
                    <td class="px-6 py-4">${event.title}</td>
                    <td class="px-6 py-4">${eventTime}</td>
                    <td class="px-6 py-4">${deletedAt}</td>
                    <td class="px-6 py-4">
                        <button type="button" class="restore-btn inline-flex items-center rounded-md bg-green-600 px-3 py-1 text-xs font-semibold text-white hover:bg-green-700" data-event-id="${event.event_id}">Restore + Repost Embed</button>
                    </td>
                `;
                deletedEventsBody.appendChild(tr);
            });
        } catch (error) {
            deletedEventsBody.innerHTML = `<tr><td colspan="4" class="text-center p-4 text-red-400">${error.message}</td></tr>`;
        }
    };

    // --- MODAL AND FORM HANDLING ---
    const populateTimezoneDropdown = () => {
        const select = document.getElementById('edit-timezone');
        select.innerHTML = '';
        for (const region in CURATED_TIMEZONES) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = region;
            CURATED_TIMEZONES[region].forEach(tz => {
                const option = document.createElement('option');
                option.value = tz;
                option.textContent = tz;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        }
    };

    const formatDateForInput = (date) => {
        if (!date) return '';
        const d = new Date(date);
        return new Date(d.getTime() - (d.getTimezoneOffset() * 60000)).toISOString().slice(0, 16);
    };

    const openEditEventModal = async (eventId) => {
        const response = await fetch(`/api/events/${eventId}`, { headers });
        if (!response.ok) throw new Error('Failed to fetch event details');
        const event = await response.json();

        editingEventIsRecurring = !!event.is_recurring;
        editEventIdInput.value = event.event_id;
        document.getElementById('edit-title').value = event.title;
        document.getElementById('edit-description').value = event.description || '';
        document.getElementById('edit-event-time').value = formatDateForInput(event.event_time);
        document.getElementById('edit-end-time').value = formatDateForInput(event.end_time);

        populateEditGameSelect(event.game_id || 'hll');
        populateEditTemplateSelect(event.template_id || null);

        populateTimezoneDropdown();
        document.getElementById('edit-timezone').value = event.timezone || 'Europe/London';

        populateRoleMultiSelect('edit-mention-role-ids', event.mention_role_ids || []);
        populateRoleMultiSelect('edit-restrict-role-ids', event.restrict_to_role_ids || []);

        document.getElementById('edit-recurrence-rule').value = event.is_recurring ? (event.recurrence_rule || 'weekly') : 'none';
        document.getElementById('edit-recreation-hours').value = event.recreation_hours || 168;
        syncRecurrenceControls('edit');

        modal.classList.remove('hidden');
    };

    upcomingEventsBody.addEventListener('click', async (e) => {
        const editButton = e.target.closest('.edit-btn');
        const deleteButton = e.target.closest('.delete-btn');
        if (editButton) {
            try {
                await openEditEventModal(editButton.dataset.eventId);
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        }
        else if (deleteButton) {
            const eventId = deleteButton.dataset.eventId;
            if (confirm('Are you sure you want to delete this event? It will move to Deleted Events and can be restored.')) {
                try {
                    const response = await fetch(`/api/events/${eventId}`, { method: 'DELETE', headers });
                    if (!response.ok) throw new Error('Failed to delete event');
                    await loadUpcomingEvents();
                    await loadDeletedEvents();
                } catch (error) {
                    alert(`Error: ${error.message}`);
                }
            }
        }
    });

    recurringEventsBody.addEventListener('click', async (e) => {
        const editButton = e.target.closest('.edit-btn');
        const deleteButton = e.target.closest('.delete-btn');
        if (editButton) {
            try {
                await openEditEventModal(editButton.dataset.eventId);
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        } 
        else if (deleteButton) {
            const eventId = deleteButton.dataset.eventId;
            if (confirm('Are you sure you want to delete this recurring event template? This will stop it from creating new events.')) {
                try {
                    const response = await fetch(`/api/events/${eventId}`, { method: 'DELETE', headers });
                    if (!response.ok) throw new Error('Failed to delete event template');
                    await loadRecurringEvents();
                    await loadDeletedEvents();
                } catch (error) {
                    alert(`Error: ${error.message}`);
                }
            }
        }
    });

    deletedEventsBody.addEventListener('click', async (e) => {
        const restoreButton = e.target.closest('.restore-btn');
        if (restoreButton) {
            const eventId = restoreButton.dataset.eventId;
            if (confirm('Restore this event and post a fresh signup embed back into Discord?')) {
                try {
                    const response = await fetch(`/api/events/${eventId}/restore`, { method: 'POST', headers });
                    if (!response.ok) throw new Error('Failed to restore event');
                    await loadDeletedEvents();
                    await loadRecurringEvents();
                    await loadUpcomingEvents();
                } catch (error) {
                    alert(`Error: ${error.message}`);
                }
            }
        }
    });

    modalCancelBtn.addEventListener('click', () => modal.classList.add('hidden'));

    editEventForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const eventId = editEventIdInput.value;
        const eventTime = new Date(document.getElementById('edit-event-time').value).toISOString();
        const endTime = new Date(document.getElementById('edit-end-time').value).toISOString();

        const recurrenceSettings = getRecurrenceSettings('edit');
        const eventData = {
            title: document.getElementById('edit-title').value,
            description: document.getElementById('edit-description').value,
            event_time: eventTime,
            end_time: endTime,
            timezone: document.getElementById('edit-timezone').value,
            game_id: document.getElementById('edit-game-id').value || 'hll',
            template_id: document.getElementById('edit-template-id').value ? parseInt(document.getElementById('edit-template-id').value, 10) : null,
            ...recurrenceSettings,
            mention_role_ids: getSelectedRoleIds('edit-mention-role-ids'),
            restrict_to_role_ids: getSelectedRoleIds('edit-restrict-role-ids')
        };
        
        try {
            const response = await fetch(`/api/events/${eventId}`, {
                method: 'PUT',
                headers: headers,
                body: JSON.stringify(eventData)
            });
            if (!response.ok) {
                 const errorData = await response.json();
                 throw new Error(errorData.detail || 'Failed to save changes.');
            }
            modal.classList.add('hidden');
            await loadUpcomingEvents();
            await loadRecurringEvents();
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    });


    if (createGameSelect) {
        createGameSelect.addEventListener('change', populateTemplateSelect);
    }

    if (editGameSelect) {
        editGameSelect.addEventListener('change', () => populateEditTemplateSelect(null));
    }

    const createRecurrenceSelect = document.getElementById('create-recurrence-rule');
    const editRecurrenceSelect = document.getElementById('edit-recurrence-rule');
    if (createRecurrenceSelect) {
        createRecurrenceSelect.addEventListener('change', () => syncRecurrenceControls('create'));
    }
    if (editRecurrenceSelect) {
        editRecurrenceSelect.addEventListener('change', () => syncRecurrenceControls('edit'));
    }

    if (createEventForm) {
        createEventForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            createEventBtn.disabled = true;
            createEventBtn.textContent = 'Creating...';
            createEventMessage.textContent = '';
            createEventMessage.className = 'text-sm mt-2 text-gray-400';

            const recurrenceSettings = getRecurrenceSettings('create');
            const payload = {
                title: document.getElementById('create-title').value.trim(),
                description: document.getElementById('create-description').value.trim(),
                event_time: new Date(document.getElementById('create-event-time').value).toISOString(),
                end_time: new Date(document.getElementById('create-end-time').value).toISOString(),
                timezone: document.getElementById('create-timezone').value,
                channel_id: document.getElementById('create-channel-id').value,
                game_id: document.getElementById('create-game-id').value || 'hll',
                template_id: document.getElementById('create-template-id').value ? parseInt(document.getElementById('create-template-id').value, 10) : null,
                ...recurrenceSettings,
                mention_role_ids: getSelectedRoleIds('create-mention-role-ids'),
                restrict_to_role_ids: getSelectedRoleIds('create-restrict-role-ids'),
                post_to_discord: document.getElementById('create-post-to-discord').checked,
            };

            try {
                const response = await fetch('/api/events', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: 'Failed to create event.' }));
                    throw new Error(errorData.detail || 'Failed to create event.');
                }
                const created = await response.json();
                createEventMessage.textContent = `Created event #${created.event_id} as ${created.game_id}.`;
                createEventMessage.className = 'text-sm mt-2 text-green-400';
                createEventForm.reset();
                populateTimezoneSelect('create-timezone');
                populateGameSelect();
                populateChannelSelect('create-channel-id');
                populateRoleMultiSelect('create-mention-role-ids');
                populateRoleMultiSelect('create-restrict-role-ids');
                syncRecurrenceControls('create');
                await loadUpcomingEvents();
                await loadRecurringEvents();
            } catch (error) {
                createEventMessage.textContent = error.message;
                createEventMessage.className = 'text-sm mt-2 text-red-400';
            } finally {
                createEventBtn.disabled = false;
                createEventBtn.textContent = 'Create Event';
            }
        });
    }

    async function loadCreateFormData() {
        const [gamesRes, templatesRes, channelsRes, rolesRes] = await Promise.all([
            fetch('/api/templates/game-systems', { headers }),
            fetch('/api/templates', { headers }),
            fetch('/api/events/channels', { headers }),
            fetch('/api/events/roles', { headers }),
        ]);
        if (!gamesRes.ok || !templatesRes.ok || !channelsRes.ok || !rolesRes.ok) throw new Error('Failed to load create event form data.');
        gameSystems = await gamesRes.json();
        squadTemplates = await templatesRes.json();
        discordChannels = await channelsRes.json();
        discordRoles = await rolesRes.json();
        populateTimezoneSelect('create-timezone');
        populateGameSelect();
        populateChannelSelect('create-channel-id');
        populateAllRoleMultiSelects();
        syncRecurrenceControls('create');
    }

    // --- INITIALIZATION ---
    loadCreateFormData().catch(error => {
        if (createEventMessage) {
            createEventMessage.textContent = error.message;
            createEventMessage.className = 'text-sm mt-2 text-red-400';
        }
        console.error(error);
    });
    loadUpcomingEvents();
    loadRecurringEvents();
    loadDeletedEvents();
});
