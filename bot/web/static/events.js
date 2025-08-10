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

    // Page sections and buttons
    const recurringView = document.getElementById('recurring-events-view');
    const deletedView = document.getElementById('deleted-events-view');
    const viewRecurringBtn = document.getElementById('view-recurring-btn');
    const viewDeletedBtn = document.getElementById('view-deleted-btn');
    const recurringEventsBody = document.getElementById('recurring-events-body');
    const deletedEventsBody = document.getElementById('deleted-events-body');
    
    // Modal elements
    const modal = document.getElementById('edit-event-modal');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const editEventForm = document.getElementById('edit-event-form');
    const editEventIdInput = document.getElementById('edit-event-id');

    // --- VIEW TOGGLING ---
    viewRecurringBtn.addEventListener('click', () => {
        recurringView.classList.remove('hidden');
        deletedView.classList.add('hidden');
        viewRecurringBtn.classList.replace('bg-gray-700', 'bg-blue-600');
        viewDeletedBtn.classList.replace('bg-blue-600', 'bg-gray-700');
    });

    viewDeletedBtn.addEventListener('click', () => {
        recurringView.classList.add('hidden');
        deletedView.classList.remove('hidden');
        viewDeletedBtn.classList.replace('bg-gray-700', 'bg-blue-600');
        viewRecurringBtn.classList.replace('bg-blue-600', 'bg-gray-700');
    });

    // --- DATA LOADING ---
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
                // --- FIX: Correctly display recurrence rule and last created time ---
                const recurrence = event.recurrence_rule ? `${event.recurrence_rule.charAt(0).toUpperCase() + event.recurrence_rule.slice(1)}` : 'N/A';
                const lastCreated = event.last_recreated_at ? new Date(event.last_recreated_at).toLocaleString() : 'N/A';

                tr.innerHTML = `
                    <td class="px-6 py-4">${event.title}</td>
                    <td class="px-6 py-4">${nextEventTime}</td>
                    <td class="px-6 py-4">${recurrence}</td>
                    <td class="px-6 py-4">${lastCreated}</td>
                    <td class="px-6 py-4">
                        <button class="edit-btn text-blue-400 hover:text-blue-600" 
                                data-event-id="${event.event_id}">Edit</button>
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
                        <button class="restore-btn text-green-400 hover:text-green-600" data-event-id="${event.event_id}">Restore</button>
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

    recurringEventsBody.addEventListener('click', async (e) => {
        if (e.target.classList.contains('edit-btn')) {
            const eventId = e.target.dataset.eventId;
            try {
                const response = await fetch(`/api/events/${eventId}`, { headers });
                if (!response.ok) throw new Error('Failed to fetch event details');
                const event = await response.json();

                editEventIdInput.value = event.event_id;
                document.getElementById('edit-title').value = event.title;
                document.getElementById('edit-description').value = event.description || '';
                document.getElementById('edit-event-time').value = formatDateForInput(event.event_time);
                document.getElementById('edit-end-time').value = formatDateForInput(event.end_time);
                
                populateTimezoneDropdown();
                document.getElementById('edit-timezone').value = event.timezone;
                
                // --- FIX: Pre-populate recurrence fields ---
                document.getElementById('edit-recurrence-rule').value = event.recurrence_rule || 'weekly';
                document.getElementById('edit-recreation-hours').value = event.recreation_hours || 168;

                modal.classList.remove('hidden');
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        }
    });

    deletedEventsBody.addEventListener('click', async (e) => {
        if (e.target.classList.contains('restore-btn')) {
            const eventId = e.target.dataset.eventId;
            if (confirm('Are you sure you want to restore this event? It will be re-posted to its original channel.')) {
                try {
                    const response = await fetch(`/api/events/${eventId}/restore`, { method: 'POST', headers });
                    if (!response.ok) throw new Error('Failed to restore event');
                    await loadDeletedEvents();
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

        const eventData = {
            title: document.getElementById('edit-title').value,
            description: document.getElementById('edit-description').value,
            event_time: eventTime,
            end_time: endTime,
            timezone: document.getElementById('edit-timezone').value,
            is_recurring: true,
            recurrence_rule: document.getElementById('edit-recurrence-rule').value,
            recreation_hours: parseInt(document.getElementById('edit-recreation-hours').value, 10),
            mention_role_ids: [],
            restrict_to_role_ids: []
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
            await loadRecurringEvents();
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    });

    // --- INITIALIZATION ---
    loadRecurringEvents();
    loadDeletedEvents();
});
