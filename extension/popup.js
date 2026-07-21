document.addEventListener('DOMContentLoaded', function() {
    const titleInput = document.getElementById('title');
    const doiInput = document.getElementById('doi');
    const authorsInput = document.getElementById('authors');
    const addBtn = document.getElementById('addBtn');
    const statusDiv = document.getElementById('status');

    let currentMetadata = null;

    // Sem content_scripts declarativos: injetamos content.js SOB DEMANDA na aba
    // ativa (activeTab + scripting) só quando o popup abre — nada roda em toda
    // página automaticamente. Depois pedimos os metadados por mensagem.
    chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
        const tab = tabs[0];
        if (!tab || !tab.id) {
            addBtn.innerText = "No paper detected";
            statusDiv.innerText = "No active tab.";
            return;
        }

        chrome.scripting.executeScript(
            { target: { tabId: tab.id }, files: ["content.js"] },
            function() {
                if (chrome.runtime.lastError) {
                    addBtn.innerText = "No paper detected";
                    statusDiv.innerText = "Cannot read this page (" +
                        chrome.runtime.lastError.message + ").";
                    return;
                }
                chrome.tabs.sendMessage(tab.id, { action: "extract_metadata" }, function(response) {
                    if (chrome.runtime.lastError || !response) {
                        addBtn.innerText = "No paper detected";
                        statusDiv.innerText = "Could not extract metadata.";
                        return;
                    }
                    currentMetadata = response;
                    // Guarda a URL da página para registrar a origem no backlog.
                    currentMetadata.source_url = tab.url || response.source_url || "";
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
                });
            }
        );
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
