document.addEventListener('DOMContentLoaded', () => {
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }

    // This script is only for the players.html page.
    const playerRatingsBody = document.getElementById('player-ratings-body');
    if (!playerRatingsBody) {
        return;
    }

    const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
    
    const syncMembersBtn = document.getElementById('sync-members-btn');
    const playerSearchInput = document.getElementById('player-search-input');
    let allPlayers = []; // Cache for player data

    const renderPlayerTable = (players) => {
        playerRatingsBody.innerHTML = '';
        if (!players || players.length === 0) {
            playerRatingsBody.innerHTML = '<tr><td colspan="5" class="text-center p-4">No players found. Try syncing members.</td></tr>';
            return;
        }
        players.forEach(player => {
            const tr = document.createElement('tr');
            tr.className = 'border-b border-gray-700';
            // --- FIX: Added new column with an input for the game_player_id ---
            tr.innerHTML = `
                <td class="px-6 py-4">${player.display_name}</td>
                <td class="px-6 py-4">
                    <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${player.is_active ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}">
                        ${player.is_active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td class="px-6 py-4">
                    <input type="number" value="${player.rating}" min="0" max="100" class="rating-input w-20 bg-gray-600 border-gray-500 rounded-md p-2" data-userid="${player.user_id}">
                </td>
                <td class="px-6 py-4">
                    <input type="text" value="${player.game_player_id || ''}" placeholder="Enter 17-digit SteamID64..." class="game-id-input w-48 bg-gray-600 border-gray-500 rounded-md p-2" data-userid="${player.user_id}">
                </td>
                <td class="px-6 py-4">
                    <button class="save-player-btn bg-blue-600 hover:bg-blue-700 text-white font-bold py-1 px-3 rounded-md text-sm" data-userid="${player.user_id}">Save</button>
                </td>
            `;
            playerRatingsBody.appendChild(tr);
        });
    };

    const loadPlayers = async () => {
        try {
            const response = await fetch('/api/players', { headers });
            if (!response.ok) throw new Error('Failed to load players');
            allPlayers = await response.json();
            // Sort by active status first, then by name
            allPlayers.sort((a, b) => {
                if (a.is_active === b.is_active) {
                    return a.display_name.localeCompare(b.display_name);
                }
                return a.is_active ? -1 : 1;
            });
            renderPlayerTable(allPlayers);
        } catch (error) {
            playerRatingsBody.innerHTML = `<tr><td colspan="5" class="text-center p-4 text-red-400">${error.message}</td></tr>`;
        }
    };

    syncMembersBtn.addEventListener('click', async () => {
        if (!confirm('This will sync all members from your Discord server. This may take a moment for large servers. Continue?')) return;
        
        syncMembersBtn.textContent = 'Syncing...';
        syncMembersBtn.disabled = true;
        try {
            // NOTE: The endpoint for this was missing from the provided files, assuming it's at /api/players/sync
            const response = await fetch('/api/players/sync', { method: 'POST', headers });
            if (!response.ok) throw new Error((await response.json()).detail || 'Sync failed');
            const result = await response.json();
            alert(result.message);
            await loadPlayers(); // Refresh the list after sync
        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            syncMembersBtn.textContent = 'Sync All Server Members';
            syncMembersBtn.disabled = false;
        }
    });

    playerSearchInput.addEventListener('input', () => {
        const searchTerm = playerSearchInput.value.toLowerCase();
        const filteredPlayers = allPlayers.filter(p => p.display_name.toLowerCase().includes(searchTerm));
        renderPlayerTable(filteredPlayers);
    });

    // --- FIX: Updated event listener to save both rating and game ID ---
    playerRatingsBody.addEventListener('click', async (e) => {
        if (e.target.classList.contains('save-player-btn')) {
            const button = e.target;
            const userId = button.dataset.userid;
            
            const ratingInput = playerRatingsBody.querySelector(`.rating-input[data-userid="${userId}"]`);
            const rating = parseInt(ratingInput.value, 10);

            const gameIdInput = playerRatingsBody.querySelector(`.game-id-input[data-userid="${userId}"]`);
            const gamePlayerId = gameIdInput.value.trim() || null;

            if (isNaN(rating) || rating < 0 || rating > 100) {
                alert('Rating must be a number between 0 and 100.');
                return;
            }

            button.textContent = 'Saving...';
            button.disabled = true;

            try {
                // Create two promises to run in parallel
                const ratingPromise = fetch('/api/players/rating', {
                    method: 'PUT',
                    headers: headers,
                    body: JSON.stringify({ user_id: userId, rating: rating })
                });

                const gameIdPromise = fetch('/api/players/game-id', {
                    method: 'PUT',
                    headers: headers,
                    body: JSON.stringify({ user_id: userId, game_player_id: gamePlayerId })
                });

                // Wait for both requests to complete
                const [ratingResponse, gameIdResponse] = await Promise.all([ratingPromise, gameIdPromise]);

                if (!ratingResponse.ok || !gameIdResponse.ok) {
                    throw new Error('Failed to save one or more fields.');
                }

                button.textContent = 'Saved!';
                setTimeout(() => { button.textContent = 'Save'; }, 2000);

            } catch (error) {
                alert(`Error: ${error.message}`);
                button.textContent = 'Save';
            } finally {
                button.disabled = false;
            }
        }
    });

    // Initial load
    loadPlayers();
});
