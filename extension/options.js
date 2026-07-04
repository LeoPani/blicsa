document.addEventListener('DOMContentLoaded', function() {
    const portInput = document.getElementById('bridgePort');
    const tokenInput = document.getElementById('bridgeToken');
    const saveBtn = document.getElementById('saveBtn');
    const statusDiv = document.getElementById('status');

    // Load existing settings
    chrome.storage.sync.get(['bridgePort', 'bridgeToken'], function(items) {
        if (items.bridgePort) portInput.value = items.bridgePort;
        if (items.bridgeToken) tokenInput.value = items.bridgeToken;
    });

    // Save settings
    saveBtn.addEventListener('click', function() {
        const port = portInput.value.trim() || '8765';
        const token = tokenInput.value.trim();

        chrome.storage.sync.set({
            bridgePort: port,
            bridgeToken: token
        }, function() {
            statusDiv.textContent = 'Options saved.';
            setTimeout(function() {
                statusDiv.textContent = '';
            }, 2000);
        });
    });
});
