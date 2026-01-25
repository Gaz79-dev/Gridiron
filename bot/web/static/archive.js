document.addEventListener('DOMContentLoaded', () => {
    // --- Authentication Check ---
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }
    const headers = { 'Authorization': `Bearer ${token}` };

    // --- DOM Elements ---
    const archiveList = document.getElementById('archive-list');
    const searchInput = document.getElementById('archive-search');
    const emptyState = document.getElementById('empty-state');
    const contentArea = document.getElementById('archive-content');
    
    // Header Elements
    const eventTitle = document.getElementById('event-title');
    const eventDate = document.getElementById('event-date');
    const eventDescPreview = document.getElementById('event-desc-preview'); // Added preview

    // Tab Elements
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    // Content Containers
    const squadContainer = document.getElementById('squad-container');
    const chatContainer = document.getElementById('chat-container');
    const transportDisplay = document.getElementById('transport-display');
    const nodesDisplay = document.getElementById('nodes-display');
    const whiteChatsDisplay = document.getElementById('white-chats-display');

    // Details Tab Elements
    const detailStartTime = document.getElementById('detail-start-time');
    const detailEndTime = document.getElementById('detail-end-time');
    const detailTimezone = document.getElementById('detail-timezone');
    const detailRestrictions = document.getElementById('detail-restrictions');
    const detailDescription = document.getElementById('detail-description');
    const detailArchivedAt = document.getElementById('detail-archived-at');

    // State
    let allArchives = [];
    let currentEventId = null;

    // --- Initialization ---
    loadArchiveList();

    // --- Event Listeners ---
    searchInput.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        const filtered = allArchives.filter(evt => evt.title.toLowerCase().includes(term));
        renderArchiveList(filtered);
    });

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // UI Toggle
            tabButtons.forEach(b => {
                b.classList.remove('bg-blue-600', 'text-white');
                b.classList.add('bg-gray-700', 'text-gray-300');
            });
            btn.classList.remove('bg-gray-700', 'text-gray-300');
            btn.classList.add('bg-blue-600', 'text-white');

            // Content Toggle
            const targetTab = btn.dataset.tab;
            tabContents.forEach(c => c.classList.add('hidden'));
            document.getElementById(`tab-${targetTab}`).classList.remove('hidden');

            // Lazy Load Chat if needed
            if (targetTab === 'chat' && currentEventId) {
                loadChatHistory(currentEventId);
            }
        });
    });

    // --- Functions ---

    async function loadArchiveList() {
        try {
            const response = await fetch('/api/archive/events', { headers });
            if (!response.ok) throw new Error('Failed to fetch archives');
            allArchives = await response.json();
            renderArchiveList(allArchives);
        } catch (error) {
            console.error(error);
            archiveList.innerHTML = `<div class="text-red-400 p-4 text-center">Error loading archives</div>`;
        }
    }

    function renderArchiveList(events) {
        archiveList.innerHTML = '';
        if (events.length === 0) {
            archiveList.innerHTML = `<div class="text-gray-500 p-4 text-center text-sm">No archived events found.</div>`;
            return;
        }

        events.forEach(evt => {
            const dateStr = new Date(evt.event_time).toLocaleDateString();
            const div = document.createElement('div');
            div.className = 'p-3 hover:bg-gray-700 cursor-pointer rounded transition-colors border-l-4 border-transparent hover:border-blue-500';
            div.innerHTML = `
                <div class="font-bold text-gray-200 truncate">${evt.title}</div>
                <div class="text-xs text-gray-400">${dateStr}</div>
            `;
            div.addEventListener('click', () => loadEventDetails(evt.event_id));
            archiveList.appendChild(div);
        });
    }

    async function loadEventDetails(eventId) {
        currentEventId = eventId;
        emptyState.classList.add('hidden');
        contentArea.classList.remove('hidden');

        // Reset Views
        squadContainer.innerHTML = '<div class="col-span-full text-center py-10">Loading roster snapshot...</div>';
        chatContainer.innerHTML = '<div class="text-center py-10 text-gray-500">Select the chat tab to load history.</div>';
        
        try {
            const response = await fetch(`/api/archive/events/${eventId}`, { headers });
            if (!response.ok) throw new Error('Failed to load event details');
            
            const data = await response.json();

            // 1. Render Header
            eventTitle.textContent = data.title;
            const dt = new Date(data.event_time);
            eventDate.textContent = dt.toLocaleString('en-GB', { dateStyle: 'full', timeStyle: 'short' });
            eventDescPreview.textContent = data.description || "No description provided.";

            // 2. Render Roster (Tab 1)
            renderRosterSnapshot(data.roster_snapshot);

            // 3. Render Plans (Tab 3)
            renderPlansSnapshot(data);

            // 4. Render Event Details (Tab 4 - New)
            renderEventDetailsTab(data);

            // Reset tabs to show Roster first
            tabButtons[0].click();

        } catch (error) {
            console.error(error);
            // alert("Error loading event archive."); 
        }
    }

    function renderEventDetailsTab(data) {
        // Time Formatter
        const formatTime = (isoString) => {
            if (!isoString) return 'N/A';
            return new Date(isoString).toLocaleString('en-GB', { dateStyle: 'full', timeStyle: 'medium' });
        };

        detailStartTime.textContent = formatTime(data.event_time);
        detailEndTime.textContent = formatTime(data.end_time);
        detailTimezone.textContent = data.timezone || 'UTC';
        detailDescription.textContent = data.description || 'No description provided.';
        detailArchivedAt.textContent = data.archived_at ? `Archived on: ${formatTime(data.archived_at)}` : '';

        // Restrictions
        if (data.restricted_roles && data.restricted_roles.length > 0) {
            detailRestrictions.innerHTML = `<span class="bg-red-900 text-red-200 px-2 py-1 rounded text-sm">Restricted to: ${data.restricted_roles.join(', ')}</span>`;
        } else {
            detailRestrictions.innerHTML = `<span class="bg-green-900 text-green-200 px-2 py-1 rounded text-sm">Open to All</span>`;
        }
    }

    function renderRosterSnapshot(rosterData) {
        squadContainer.innerHTML = '';
        if (!rosterData || Object.keys(rosterData).length === 0) {
            squadContainer.innerHTML = '<div class="col-span-full text-center text-gray-500 italic">No roster data saved for this event.</div>';
            return;
        }

        // --- SORTING LOGIC ---
        const squadList = Object.entries(rosterData).map(([name, rawMembers]) => {
            let members = rawMembers;
            // Handle if database returns stringified JSON
            if (typeof members === 'string') {
                try {
                    members = JSON.parse(members);
                } catch (e) {
                    console.error("Failed to parse members JSON:", e);
                    members = [];
                }
            }
            return { name, members };
        });

        // Custom Sort Function
        squadList.sort((a, b) => {
            const getRank = (name) => {
                const n = name.toLowerCase();
                if (n.includes('commander')) return -100;
                if (n.includes('reserves')) return 9999;
                if (n.includes('artillery')) return 100;
                const match = name.match(/(\d+(\.\d+)?)/);
                if (match) return parseFloat(match[0]);
                return 50;
            };
            const rankA = getRank(a.name);
            const rankB = getRank(b.name);
            if (rankA === rankB) return a.name.localeCompare(b.name);
            return rankA - rankB;
        });

        // --- RENDER ---
        squadList.forEach(squad => {
            const squadName = squad.name;
            const members = squad.members;

            const card = document.createElement('div');
            card.className = 'bg-gray-800 rounded shadow border border-gray-700 overflow-hidden';

            let membersHtml = '';
            if (Array.isArray(members) && members.length > 0) {
                members.forEach(m => {
                    const role = m.role_name || m.assigned_role_name || "Unknown";
                    membersHtml += `
                        <div class="px-3 py-2 border-b border-gray-700 last:border-0 flex justify-between items-center text-sm">
                            <span class="text-gray-200">${m.display_name}</span>
                            <span class="text-xs text-gray-500 bg-gray-900 px-2 py-0.5 rounded">${role}</span>
                        </div>
                    `;
                });
            }

            card.innerHTML = `
                <div class="bg-gray-700 px-3 py-2 font-bold text-gray-200 text-sm flex justify-between">
                    <span>${squadName}</span>
                    <span class="text-xs bg-gray-600 px-2 rounded-full">${Array.isArray(members) ? members.length : 0}</span>
                </div>
                <div>${membersHtml || '<div class="p-3 text-xs text-gray-500 italic">Empty Squad</div>'}</div>
            `;
            squadContainer.appendChild(card);
        });
    }

    async function loadChatHistory(eventId) {
        chatContainer.innerHTML = '<div class="text-center py-4">Loading chat history...</div>';
        
        try {
            const response = await fetch(`/api/archive/events/${eventId}/chat`, { headers });
            if (!response.ok) throw new Error("Failed to load chat");
            
            const messages = await response.json();
            renderChat(messages);
        } catch (error) {
            console.error(error);
            chatContainer.innerHTML = '<div class="text-center text-red-400 py-4">Could not load chat history.</div>';
        }
    }

    function renderChat(messages) {
        chatContainer.innerHTML = '';
        if (!messages || messages.length === 0) {
            chatContainer.innerHTML = '<div class="text-center text-gray-500 py-10">No chat history recorded for this event.</div>';
            return;
        }

        messages.forEach(msg => {
            const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const date = new Date(msg.timestamp).toLocaleDateString();
            
            // Build attachments HTML
            let attachmentsHtml = '';
            if (msg.attachment_urls && Array.isArray(msg.attachment_urls) && msg.attachment_urls.length > 0) {
                msg.attachment_urls.forEach(url => {
                    if (url.match(/\.(jpeg|jpg|gif|png|webp)$/i)) {
                        attachmentsHtml += `<div class="mt-2"><a href="${url}" target="_blank"><img src="${url}" class="max-w-xs rounded border border-gray-700 max-h-60 object-contain hover:opacity-90"></a></div>`;
                    } else {
                        attachmentsHtml += `<div class="mt-1"><a href="${url}" target="_blank" class="text-blue-400 text-xs hover:underline">📎 Attachment</a></div>`;
                    }
                });
            }

            const msgDiv = document.createElement('div');
            msgDiv.className = 'discord-msg flex px-4 py-2 mt-1';
            msgDiv.innerHTML = `
                <img src="${msg.avatar_url || '/static/default_avatar.png'}" class="discord-avatar rounded-full mr-4 bg-gray-600" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
                <div class="flex-grow min-w-0">
                    <div class="flex items-baseline">
                        <span class="font-semibold text-white mr-2 text-sm">${msg.user_name}</span>
                        <span class="text-xs text-gray-500">${date} at ${time}</span>
                    </div>
                    <div class="text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">${msg.content}</div>
                    ${attachmentsHtml}
                </div>
            `;
            chatContainer.appendChild(msgDiv);
        });
        
        // Scroll to bottom
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function renderPlansSnapshot(data) {
        // 1. Transport
        const transport = data.transport_snapshot || {};
        const transportAssignments = transport.assignments || {}; 
        
        const transportDisplay = document.getElementById('transport-display');
        transportDisplay.innerHTML = '';

        if (Object.keys(transportAssignments).length === 0) {
            transportDisplay.innerHTML = '<p class="text-gray-500 italic">No transport plan saved.</p>';
        } else {
            // Sort HQs (HQ1, HQ2, HQ3)
            const sortedHQs = Object.keys(transportAssignments).sort();
            
            for (const hqName of sortedHQs) {
                const squads = transportAssignments[hqName];
                if (squads && squads.length > 0) {
                    const row = document.createElement('div');
                    row.className = 'flex items-start border-l-2 border-blue-500 pl-3 py-1';
                    row.innerHTML = `
                        <div class="font-bold text-gray-300 w-16">${hqName}:</div>
                        <div class="text-gray-400 text-sm flex-1">${squads.join(', ')}</div>
                    `;
                    transportDisplay.appendChild(row);
                }
            }
        }

        // 2. Nodes
        const nodes = data.nodes_snapshot || {};
        const nodesDisplay = document.getElementById('nodes-display');
        
        if (Object.keys(nodes).length === 0) {
            nodesDisplay.innerHTML = '<p class="text-gray-500 italic">No nodes plan saved.</p>';
        } else {
            // Basic rendering of key-value pairs for nodes
            let html = '<div class="space-y-2">';
            for (const [key, val] of Object.entries(nodes)) {
                 html += `<div class="text-sm"><span class="text-gray-400">${key}:</span> <span class="text-gray-200">${val}</span></div>`;
            }
            html += '</div>';
            nodesDisplay.innerHTML = html;
        }

        // 3. White Chats
        const whiteChats = data.white_chats_snapshot || [];
        const wcDisplay = document.getElementById('white-chats-display');
        wcDisplay.innerHTML = '';

        if (!whiteChats || whiteChats.length === 0) {
            wcDisplay.innerHTML = '<p class="text-gray-500 italic col-span-full">No white chats recorded.</p>';
        } else {
            whiteChats.forEach(chat => {
                const card = document.createElement('div');
                card.className = 'bg-gray-700 p-3 rounded border border-gray-600';
                
                let membersList = '';
                if (chat.members && Array.isArray(chat.members)) {
                    membersList = chat.members.map(m => 
                        `<li class="text-gray-300 text-xs py-0.5">• ${m.display_name}</li>`
                    ).join('');
                }

                card.innerHTML = `
                    <h4 class="font-bold text-white text-sm mb-2 border-b border-gray-600 pb-1">
                        ${chat.name}
                    </h4>
                    <ul class="list-none pl-1 space-y-1">
                        ${membersList || '<li class="text-gray-500 text-xs italic">Empty</li>'}
                    </ul>
                `;
                wcDisplay.appendChild(card);
            });
        }
    }
});
