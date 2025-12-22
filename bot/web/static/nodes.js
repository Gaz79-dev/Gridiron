document.addEventListener('DOMContentLoaded', () => {
    const sendNodesBtn = document.getElementById('send-nodes-btn');
    const eventDropdown = document.getElementById('event-dropdown');
    const channelDropdown = document.getElementById('channel-dropdown');

    if (sendNodesBtn) {
        sendNodesBtn.addEventListener('click', async () => {
            const eventId = eventDropdown.value;
            const channelId = channelDropdown.value;
            const token = localStorage.getItem('accessToken');

            if (!eventId || !channelId) {
                alert("Please select an event and a target Discord channel.");
                return;
            }

            try {
                sendNodesBtn.disabled = true;
                sendNodesBtn.textContent = 'Sending...';

                const response = await fetch(`/api/events/${eventId}/send-nodes-embed`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ channel_id: channelId })
                });

                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || 'Failed to send nodes embed');
                }

                alert('Nodes Building Plan embed sent to Discord!');
            } catch (error) {
                alert(`Error: ${error.message}`);
            } finally {
                sendNodesBtn.disabled = false;
                sendNodesBtn.textContent = 'Send Nodes Plan';
            }
        });
    }
});
