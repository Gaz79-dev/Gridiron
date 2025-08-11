document.addEventListener('DOMContentLoaded', () => {
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }

    // This script is only for the stats.html page.
    const uploadForm = document.getElementById('upload-stats-form');
    if (!uploadForm) {
        return;
    }

    const headers = { 'Authorization': `Bearer ${token}` };
    
    // --- Element Selectors ---
    const leaderboardsContainer = document.getElementById('leaderboards-container');
    const exportStatsBtn = document.getElementById('export-stats-btn');
    const uploadBtn = document.getElementById('upload-btn');

    // --- Functions ---

    const renderLeaderboard = (title, data) => {
        const boardDiv = document.createElement('div');
        boardDiv.className = 'bg-gray-700 p-4 rounded-lg';
        
        let tableRows = '';
        if (data && data.length > 0) {
            data.forEach((player, index) => {
                tableRows += `
                    <tr class="border-b border-gray-600">
                        <td class="py-2 px-3 text-sm">${index + 1}</td>
                        <td class="py-2 px-3 text-sm">${player.player_name}</td>
                        <td class="py-2 px-3 text-sm font-bold text-right">${player.total_value}</td>
                    </tr>
                `;
            });
        } else {
            tableRows = '<tr><td colspan="3" class="text-center py-4 text-gray-500">No data available.</td></tr>';
        }

        boardDiv.innerHTML = `
            <h3 class="text-lg font-semibold text-white mb-3">${title}</h3>
            <table class="w-full">
                <thead>
                    <tr class="border-b border-gray-500">
                        <th class="py-2 px-3 text-left text-xs font-medium uppercase">#</th>
                        <th class="py-2 px-3 text-left text-xs font-medium uppercase">Player</th>
                        <th class="py-2 px-3 text-right text-xs font-medium uppercase">Total</th>
                    </tr>
                </thead>
                <tbody>
                    ${tableRows}
                </tbody>
            </table>
        `;
        leaderboardsContainer.appendChild(boardDiv);
    };

    const loadLeaderboards = async () => {
        try {
            const response = await fetch('/api/stats/leaderboards', { headers });
            if (!response.ok) throw new Error('Failed to load leaderboards');
            const data = await response.json();
            
            leaderboardsContainer.innerHTML = ''; // Clear previous data
            renderLeaderboard('Top 10 Kills', data.kills);
            renderLeaderboard('Top 10 Combat Effectiveness', data.combat_effectiveness);
            renderLeaderboard('Top 10 Support Score', data.support_score);

        } catch (error) {
            leaderboardsContainer.innerHTML = `<p class="text-red-400 col-span-full">${error.message}</p>`;
        }
    };

    // --- Event Listeners ---

    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const eventName = document.getElementById('event-name').value;
        const eventDate = document.getElementById('event-date').value;
        const csvFile = document.getElementById('csv-file').files[0];

        if (!eventName || !eventDate || !csvFile) {
            alert('Please fill out all fields and select a file.');
            return;
        }

        const formData = new FormData();
        formData.append('event_name', eventName);
        formData.append('event_date', eventDate);
        formData.append('file', csvFile);

        uploadBtn.textContent = 'Uploading...';
        uploadBtn.disabled = true;

        try {
            const response = await fetch('/api/stats/upload', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }, // No Content-Type, browser sets it for FormData
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Upload failed');
            }

            const result = await response.json();
            alert(result.message);
            uploadForm.reset();
            await loadLeaderboards(); // Refresh leaderboards after successful upload

        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            uploadBtn.textContent = 'Upload Stats';
            uploadBtn.disabled = false;
        }
    });

    exportStatsBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/api/stats/export', { headers });
            if (!response.ok) throw new Error('Failed to generate export');
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `player_stats_export_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    });

    // --- Initial Load ---
    loadLeaderboards();
});
