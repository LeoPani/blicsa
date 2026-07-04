chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "add_paper") {
        chrome.storage.sync.get(['bridgePort', 'bridgeToken'], function(items) {
            const port = items.bridgePort || '8765';
            const token = items.bridgeToken || '';

            if (!token) {
                sendResponse({success: false, error: "Bridge token not configured. Please open extension options."});
                return;
            }

            const url = `http://127.0.0.1:${port}/api/add`;
            
            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(request.metadata)
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                sendResponse({success: true, data: data});
            })
            .catch(error => {
                sendResponse({success: false, error: error.toString()});
            });
        });
        
        return true; // Indicates asynchronous response
    }
});
