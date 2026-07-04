document.addEventListener('DOMContentLoaded', function() {
    const titleInput = document.getElementById('title');
    const doiInput = document.getElementById('doi');
    const authorsInput = document.getElementById('authors');
    const addBtn = document.getElementById('addBtn');
    const statusDiv = document.getElementById('status');

    let currentMetadata = null;

    // Ask content script for metadata
    chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
        chrome.tabs.sendMessage(tabs[0].id, {action: "extract_metadata"}, function(response) {
            if (response) {
                currentMetadata = response;
                titleInput.value = response.title || '';
                doiInput.value = response.doi || '';
                authorsInput.value = response.authors || '';
                
                if (response.doi || response.title) {
                    addBtn.disabled = false;
                    addBtn.innerText = "Add to Corpus";
                } else {
                    addBtn.innerText = "No paper detected";
                    statusDiv.innerText = "Could not find DOI or title on this page.";
                }
            } else {
                addBtn.innerText = "No paper detected";
                statusDiv.innerText = "Could not extract metadata.";
            }
        });
    });

    addBtn.addEventListener('click', function() {
        if (!currentMetadata) return;

        addBtn.disabled = true;
        addBtn.innerText = "Adding...";
        statusDiv.innerText = "";
        statusDiv.className = "";

        chrome.runtime.sendMessage({action: "add_paper", metadata: currentMetadata}, function(response) {
            if (response && response.success) {
                statusDiv.innerText = `Success! Corpus count: ${response.data.count}`;
                statusDiv.className = "success";
                addBtn.innerText = "Added";
            } else {
                const err = response ? response.error : "Unknown error";
                statusDiv.innerText = `Error: ${err}`;
                statusDiv.className = "error";
                addBtn.disabled = false;
                addBtn.innerText = "Try Again";
            }
        });
    });
});
