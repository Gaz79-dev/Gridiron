document.addEventListener('DOMContentLoaded', () => {
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }
    const headers = { 'Authorization': `Bearer ${token}` };
    const tableBody = document.getElementById('events-table-body');
    const pageTitle = document.getElementById('page-title');
    
    const pathParts = window.location.pathname.split('/');
    const userId = pathParts[pathParts.length - 1];
    
    // --- ADDITION: Get player name from URL query parameter ---
    const urlParams = new URLSearchParams(window.location.search);
    const playerName = urlParams.get('name');

    if (playerName) {
        pageTitle.textContent = `Event History for ${decodeURIComponent(playerName)}`;
    }
    // --- END ADDITION ---

    if (!userId) {
        // --- START: MODIFICATION - Update colspan ---
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center p-8 text-red-400">Could not identify the player.</td></tr>';
        // --- END: MODIFICATION ---
        return;
    }

    // --- START: FIX ---
    // The API endpoint was renamed from /accepted-events to /event-history
    // in bot/api/stats.py. This updates the fetch call to match.
    fetch(`/api/stats/player/${userId}/event-history`, { headers })
    // --- END: FIX ---
        .then(response => {
            if (!response.ok) {
                // --- START: FIX ---
                // Add more detailed error logging
                console.error('API Response Status:', response.status);
                response.json().then(err => console.error('API Error Detail:', err.detail));
                throw new Error(`Failed to fetch event history (${response.status})`);
                // --- END: FIX ---
            }
            return response.json();
        })
        .then(data => {
            tableBody.innerHTML = '';
            if (data.length === 0) {
                // --- START: MODIFICATION - Update colspan ---
                tableBody.innerHTML = '<tr><td colspan="6" class="text-center p-8">This player has no event history.</td></tr>';
                // --- END: MODIFICATION ---
                return;
            }
            data.forEach(event => {
                const tr = document.createElement('tr');
                tr.className = 'border-b border-gray-700';
                
                // --- START: MODIFICATION - Render new columns ---
                const eventStart = new Date(event.event_time).toLocaleString('en-GB', {
                    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
                });
                const eventEnd = event.end_time ? new Date(event.end_time).toLocaleString('en-GB', {
                    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
                }) : 'N/A';

                let rsvpClass = '';
                if (event.rsvp_status === 'Accepted') rsvpClass = 'text-green-400';
                if (event.rsvp_status === 'Tentative') rsvpClass = 'text-yellow-400';
                if (event.rsvp_status === 'Declined') rsvpClass = 'text-red-400';

                tr.innerHTML = `
                    <td class="px-6 py-4 whitespace-nowrap">${event.event_title}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${eventStart}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${eventEnd}</td>
                    <td class="px-6 py-4 whitespace-nowrap font-bold ${rsvpClass}">${event.rsvp_status || 'N/A'}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${event.role_name || 'N/A'}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${event.subclass_name || 'N/A'}</td>
                `;
                // --- END: MODIFICATION ---
                tableBody.appendChild(tr);
            });
        })
        .catch(error => {
            console.error('Error loading event history:', error);
            // --- START: MODIFICATION - Update colspan ---
            tableBody.innerHTML = '<tr><td colspan="6" class="text-center p-8 text-red-400">Could not load event history.</td></tr>';
            // --- END: MODIFICATION ---
        });
});
