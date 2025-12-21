document.addEventListener('DOMContentLoaded', () => {
    // --- Shared State & Configuration ---
    const token = localStorage.getItem('accessToken');
    if (!token) return; // Main auth handled by main-v2.js, but safety check here

    const headers = { 
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json' 
    };

    // --- DOM Elements ---
    // These IDs must match what we will add to index.html in the next step
    const wcSection = document.getElementById('white-chat-section');
    const wcContainer = document.getElementById('white-chats-list'); 
    const wcCountInput = document.getElementById('white-chat-count');
    const createWcBtn = document.getElementById('create-white-chats-btn');
    const sendWcBtn = document.getElementById('send-white-chats-btn');
    
    // Elements from main page structure
    const eventDropdown = document.getElementById('event-dropdown');
    const channelDropdown = document.getElementById('channel-dropdown');

    // --- State ---
    let currentWhiteChats = [];
    let squadPlayers = []; // List of players currently assigned to squads (candidates)

    // --- 1. Event Listeners ---
    
    // Listen for event changes to load the relevant data
    if (eventDropdown) {
        eventDropdown.addEventListener('change', () => {
            const eventId = eventDropdown.value;
            if (eventId) {
                if (wcSection) wcSection.classList.remove('hidden');
                refreshData(eventId);
            } else {
                if (wcSection) wcSection.classList.add('hidden');
            }
        });
    }

    if (createWcBtn) {
        createWcBtn.addEventListener('click', async () => {
            const eventId = eventDropdown.value;
            const count = parseInt(wcCountInput.value);
            
            if (!eventId) {
                alert("Please select an event first.");
                return;
            }
            if (!count || count < 1) {
                alert("Please enter a valid number of parties (minimum 1).");
                return;
            }

            if (confirm(`This will delete any existing white chats for this event and create ${count} new ones. Continue?`)) {
                await createWhiteChats(eventId, count);
            }
        });
    }

    if (sendWcBtn) {
        sendWcBtn.addEventListener('click', async () => {
            const eventId = eventDropdown.value;
            const channelId = channelDropdown ? channelDropdown.value : null;
            
            if (!eventId || !channelId) {
                alert("Please select an event and a target Discord channel.");
                return;
            }
            await sendWhiteChatEmbed(eventId, channelId);
        });
    }

    // --- 2. Data Handling & API Calls ---

    async function refreshData(eventId) {
        // Load both the white chats and the squad players (candidates) in parallel
        await Promise.all([
            loadWhiteChats(eventId),
            fetchSquadPlayers(eventId)
        ]);
    }

    async function loadWhiteChats(eventId) {
        try {
            const response = await fetch(`/api/white-chats/event/${eventId}`, { headers });
            if (!response.ok) throw new Error('Failed to load white chats');
            
            currentWhiteChats = await response.json();
            renderWhiteChats(eventId);
        } catch (err) {
            console.error("Error loading white chats:", err);
            if (wcContainer) wcContainer.innerHTML = '<p class="text-red-400 text-sm">Error loading white chats.</p>';
        }
    }

    async function fetchSquadPlayers(eventId) {
        try {
            // We fetch the squads to determine who is "placed in a squad"
            const response = await fetch(`/api/events/${eventId}/squads`, { headers });
            if (!response.ok) throw new Error('Failed to load squads for candidates');
            
            const squads = await response.json();
            squadPlayers = [];

            // Flatten squad list into a list of players
            squads.forEach(squad => {
                // Include everyone assigned to a squad (including Reserves if desired)
                squad.members.forEach(member => {
                    squadPlayers.push({
                        user_id: member.user_id,
                        display_name: member.display_name,
                        squad_name: squad.name
                    });
                });
            });
            
            // Sort alphabetically for easier searching in dropdown
            squadPlayers.sort((a, b) => a.display_name.localeCompare(b.display_name));
            
            // Re-render to populate dropdowns
            renderWhiteChats(eventId);
        } catch (err) {
            console.error("Error fetching squad players:", err);
        }
    }

    async function createWhiteChats(eventId, count) {
        try {
            createWcBtn.disabled = true;
            createWcBtn.textContent = 'Creating...';
            
            const response = await fetch(`/api/white-chats/event/${eventId}/create`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ count: count })
            });
            
            if (!response.ok) throw new Error('Failed to create white chats');
            
            await refreshData(eventId);
        } catch (err) {
            alert(`Error: ${err.message}`);
        } finally {
            createWcBtn.disabled = false;
            createWcBtn.textContent = 'Create / Reset';
        }
    }

    async function addMember(chatId, userId, eventId) {
        try {
            const response = await fetch(`/api/white-chats/${chatId}/members`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ user_id: userId })
            });
            
            if (!response.ok) throw new Error('Failed to add member');
            await loadWhiteChats(eventId); // Reload to see changes
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    }

    async function removeMember(chatId, userId, eventId) {
        try {
            const response = await fetch(`/api/white-chats/${chatId}/members/${userId}`, {
                method: 'DELETE',
                headers
            });
            
            if (!response.ok) throw new Error('Failed to remove member');
            await loadWhiteChats(eventId); // Reload to see changes
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    }

    async function sendWhiteChatEmbed(eventId, channelId) {
        try {
            sendWcBtn.disabled = true;
            sendWcBtn.textContent = 'Sending...';
            
            const response = await fetch(`/api/white-chats/event/${eventId}/notify`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ channel_id: channelId })
            });
            
            if (!response.ok) throw new Error('Failed to send notification');
            alert('White Chat embed sent to Discord!');
        } catch (err) {
            alert(`Error: ${err.message}`);
        } finally {
            sendWcBtn.disabled = false;
            sendWcBtn.textContent = 'Send to Discord';
        }
    }

    // --- 3. UI Rendering ---

    function renderWhiteChats(eventId) {
        if (!wcContainer) return;
        wcContainer.innerHTML = '';

        if (!currentWhiteChats || currentWhiteChats.length === 0) {
            wcContainer.innerHTML = '<p class="text-gray-500 text-sm italic col-span-full text-center">No white chats created. Enter a number and click Create.</p>';
            return;
        }

        currentWhiteChats.forEach(chat => {
            // Card Container
            const card = document.createElement('div');
            card.className = 'bg-gray-800 rounded-lg p-4 shadow border border-gray-700 flex flex-col gap-2';

            // Title
            const title = document.createElement('h3');
            title.className = 'text-white font-bold text-center border-b border-gray-600 pb-2 mb-2';
            title.textContent = chat.name;
            card.appendChild(title);

            // Members List Container
            const memberList = document.createElement('div');
            memberList.className = 'flex-grow space-y-2 mb-2';
            
            if (chat.members.length === 0) {
                memberList.innerHTML = '<p class="text-xs text-gray-500 text-center italic">Empty</p>';
            } else {
                chat.members.forEach(member => {
                    const row = document.createElement('div');
                    row.className = 'flex justify-between items-center bg-gray-700 px-2 py-1 rounded text-sm text-gray-200';
                    
                    const nameSpan = document.createElement('span');
                    nameSpan.textContent = member.display_name;
                    nameSpan.className = 'truncate max-w-[150px]';
                    
                    const removeBtn = document.createElement('button');
                    removeBtn.className = 'text-red-400 hover:text-red-300 font-bold ml-2 px-1';
                    removeBtn.innerHTML = '&times;';
                    removeBtn.title = 'Remove';
                    removeBtn.onclick = () => removeMember(chat.id, member.user_id, eventId);
                    
                    row.appendChild(nameSpan);
                    row.appendChild(removeBtn);
                    memberList.appendChild(row);
                });
            }
            card.appendChild(memberList);

            // Control Area (Dropdown + Add Button)
            const controlDiv = document.createElement('div');
            controlDiv.className = 'mt-auto pt-2 border-t border-gray-600';
            
            const select = document.createElement('select');
            select.className = 'w-full bg-gray-900 text-gray-300 text-xs p-1 rounded mb-2 border border-gray-600 focus:border-blue-500 focus:outline-none';
            
            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "Select Player...";
            select.appendChild(defaultOption);

            // Populate with candidates (Players in squads)
            squadPlayers.forEach(p => {
                // Filter: Don't show players already in THIS party
                const alreadyInThis = chat.members.some(m => m.user_id === p.user_id);
                if (!alreadyInThis) {
                    const opt = document.createElement('option');
                    opt.value = p.user_id;
                    opt.textContent = `${p.display_name} (${p.squad_name})`;
                    select.appendChild(opt);
                }
            });

            const addBtn = document.createElement('button');
            addBtn.className = 'w-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold py-1 rounded transition-colors';
            addBtn.textContent = 'Add Player';
            addBtn.onclick = () => {
                const selectedUserId = select.value;
                if (selectedUserId) {
                    addMember(chat.id, selectedUserId, eventId);
                }
            };

            controlDiv.appendChild(select);
            controlDiv.appendChild(addBtn);
            card.appendChild(controlDiv);

            wcContainer.appendChild(card);
        });
    }
});
