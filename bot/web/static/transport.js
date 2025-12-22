document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const eventDropdown = document.getElementById('event-dropdown');
    const channelDropdown = document.getElementById('channel-dropdown');
    const transportSection = document.getElementById('transport-section');
    const transportContainer = document.getElementById('transport-builder-area');
    const sendTransportBtn = document.getElementById('send-transport-btn');
    const saveTransportBtn = document.getElementById('save-transport-btn'); // NEW

    // Config
    const HQS = ['HQ1', 'HQ2', 'HQ3'];
    const token = localStorage.getItem('accessToken');
    const headers = { 
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json' 
    };

    // State
    let squadList = [];
    let drivers = { HQ1: [], HQ2: [], HQ3: [] };
    let savedAssignments = { HQ1: [], HQ2: [], HQ3: [] }; // Store loaded state

    // --- Listeners ---
    if (eventDropdown) {
        eventDropdown.addEventListener('change', () => {
            const eventId = eventDropdown.value;
            if (eventId) {
                if (transportSection) transportSection.classList.remove('hidden');
                loadTransportData(eventId);
            } else {
                if (transportSection) transportSection.classList.add('hidden');
            }
        });
    }

    if (sendTransportBtn) {
        sendTransportBtn.addEventListener('click', async () => {
            await sendTransportEmbed();
        });
    }

    if (saveTransportBtn) {
        saveTransportBtn.addEventListener('click', async () => {
            await saveTransportAssignments();
        });
    }

    // NEW: Listen for checkbox changes to enforce exclusivity
    if (transportContainer) {
        transportContainer.addEventListener('change', (e) => {
            if (e.target.classList.contains('transport-squad-checkbox')) {
                updateCheckboxStates();
            }
        });
    }

    // --- Logic: Prevent Duplicate Selections ---
    function updateCheckboxStates() {
        const allCheckboxes = document.querySelectorAll('.transport-squad-checkbox');
        
        // 1. Find out which squads are currently selected
        const selectedSquads = new Set();
        allCheckboxes.forEach(cb => {
            if (cb.checked) {
                selectedSquads.add(cb.value);
            }
        });

        // 2. Disable those squads in other lists
        allCheckboxes.forEach(cb => {
            if (!cb.checked) {
                if (selectedSquads.has(cb.value)) {
                    cb.disabled = true;
                    cb.parentElement.classList.add('opacity-50', 'cursor-not-allowed');
                    cb.parentElement.title = "Squad already assigned to another HQ";
                } else {
                    cb.disabled = false;
                    cb.parentElement.classList.remove('opacity-50', 'cursor-not-allowed');
                    cb.parentElement.removeAttribute('title');
                }
            }
        });
    }

    // --- Data Loading ---
    async function loadTransportData(eventId) {
        try {
            // Parallel fetch: Squads AND Saved Assignments
            const [squadsRes, assignmentsRes] = await Promise.all([
                fetch(`/api/events/${eventId}/squads`, { headers }),
                fetch(`/api/events/${eventId}/transport`, { headers })
            ]);

            if (!squadsRes.ok) throw new Error('Failed to load squads');
            const squads = await squadsRes.json();
            
            if (assignmentsRes.ok) {
                const data = await assignmentsRes.json();
                savedAssignments = data.assignments || { HQ1: [], HQ2: [], HQ3: [] };
            } else {
                savedAssignments = { HQ1: [], HQ2: [], HQ3: [] };
            }
            
            processSquadData(squads);
            renderTransportBuilder();
        } catch (err) {
            console.error("Error loading transport data:", err);
            if (transportContainer) transportContainer.innerHTML = '<p class="text-red-400">Error loading data.</p>';
        }
    }

    function processSquadData(squads) {
        // Reset state
        squadList = [];
        drivers = { HQ1: [], HQ2: [], HQ3: [] };

        squads.forEach(squad => {
            if (squad.name !== 'Reserves') {
                squadList.push(squad.name);
            }

            // Find drivers in this squad
            squad.members.forEach(m => {
                if (!m.startup_task) return;
                
                // Regex for HQx ... Driver
                const match = m.startup_task.match(/HQ([1-3])\s+(.*)/i);
                if (match) {
                    const hqNum = `HQ${match[1]}`;
                    const taskLower = match[2].toLowerCase();
                    if (taskLower.includes('driver') || taskLower.includes('transport')) {
                        drivers[hqNum].push(m.display_name);
                    }
                }
            });
        });
        
        // Sort squads for dropdown
        squadList.sort();
    }

    // --- Rendering ---
    function renderTransportBuilder() {
        if (!transportContainer) return;
        transportContainer.innerHTML = '';

        const grid = document.createElement('div');
        grid.className = 'grid grid-cols-1 md:grid-cols-3 gap-6';

        HQS.forEach(hq => {
            const card = document.createElement('div');
            card.className = 'bg-gray-700 rounded p-4 border border-gray-600';

            // Header
            const header = document.createElement('h3');
            header.className = 'text-lg font-bold text-center text-blue-300 border-b border-gray-500 pb-2 mb-2';
            header.textContent = `${hq} Location`;
            card.appendChild(header);

            // Drivers List
            const driverTitle = document.createElement('h4');
            driverTitle.className = 'text-xs uppercase text-gray-400 font-bold mb-1';
            driverTitle.textContent = 'Drivers:';
            card.appendChild(driverTitle);

            const driverListDiv = document.createElement('div');
            driverListDiv.className = 'mb-4 text-sm text-white bg-gray-800 p-2 rounded min-h-[30px]';
            if (drivers[hq].length > 0) {
                driverListDiv.textContent = drivers[hq].join(', ');
            } else {
                driverListDiv.textContent = 'None assigned';
                driverListDiv.className += ' italic text-gray-500';
            }
            card.appendChild(driverListDiv);

            // Squad Assignments (Multi-select / Checkboxes)
            const squadTitle = document.createElement('h4');
            squadTitle.className = 'text-xs uppercase text-gray-400 font-bold mb-1';
            squadTitle.textContent = 'Deploying Squads:';
            card.appendChild(squadTitle);

            const squadContainer = document.createElement('div');
            squadContainer.className = 'bg-gray-800 p-2 rounded max-h-40 overflow-y-auto space-y-1';
            
            // Get saved list for this HQ to pre-check
            const preCheckedSquads = new Set(savedAssignments[hq] || []);

            squadList.forEach(squadName => {
                const label = document.createElement('label');
                label.className = 'flex items-center space-x-2 text-sm cursor-pointer hover:bg-gray-700 p-1 rounded transition-opacity';
                
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.value = squadName;
                checkbox.dataset.hq = hq;
                checkbox.className = 'form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-500 rounded transport-squad-checkbox';
                
                // Pre-check if in saved list
                if (preCheckedSquads.has(squadName)) {
                    checkbox.checked = true;
                }

                const span = document.createElement('span');
                span.textContent = squadName;

                label.appendChild(checkbox);
                label.appendChild(span);
                squadContainer.appendChild(label);
            });
            card.appendChild(squadContainer);

            grid.appendChild(card);
        });

        transportContainer.appendChild(grid);
        
        // Initial run to ensure clean state and enforce exclusivity based on loaded data
        updateCheckboxStates();
    }

    function collectAssignments() {
        const assignments = { HQ1: [], HQ2: [], HQ3: [] };
        const checkboxes = transportContainer.querySelectorAll('input[type="checkbox"]:checked');
        
        checkboxes.forEach(cb => {
            const hq = cb.dataset.hq;
            if (assignments[hq]) {
                assignments[hq].push(cb.value);
            }
        });
        return assignments;
    }

    // --- Actions ---
    async function saveTransportAssignments() {
        const eventId = eventDropdown.value;
        if (!eventId) return;

        const assignments = collectAssignments();

        try {
            saveTransportBtn.disabled = true;
            saveTransportBtn.textContent = 'Saving...';

            const response = await fetch(`/api/events/${eventId}/transport`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ assignments })
            });

            if (!response.ok) throw new Error('Failed to save');
            
            // Update local state
            savedAssignments = assignments;
            
            // Visual feedback
            const originalText = saveTransportBtn.textContent;
            saveTransportBtn.textContent = 'Saved!';
            setTimeout(() => { 
                saveTransportBtn.textContent = 'Save Selection'; 
                saveTransportBtn.disabled = false;
            }, 1000);

        } catch (error) {
            alert(`Save failed: ${error.message}`);
            saveTransportBtn.disabled = false;
            saveTransportBtn.textContent = 'Save Selection';
        }
    }

    async function sendTransportEmbed() {
        const eventId = eventDropdown.value;
        const channelId = channelDropdown ? channelDropdown.value : null;

        if (!eventId || !channelId) {
            alert("Please select an event and a target Discord channel.");
            return;
        }

        const assignments = collectAssignments();
        const payload = {
            channel_id: channelId,
            assignments: assignments
        };

        try {
            sendTransportBtn.disabled = true;
            sendTransportBtn.textContent = 'Sending...';

            const response = await fetch(`/api/events/${eventId}/send-transport-embed`, {
                method: 'POST',
                headers,
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Failed to send transport embed');
            }

            alert('Transport & Deployment embed sent to Discord!');
            
            // Since send also saves, update local state
            savedAssignments = assignments;

        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            sendTransportBtn.disabled = false;
            sendTransportBtn.textContent = 'Send Transport Plan';
        }
    }
});
