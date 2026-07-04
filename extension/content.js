function extractMetadata() {
    let metadata = {
        title: '',
        doi: '',
        authors: ''
    };

    // 1. Try to extract from meta tags
    const titleMeta = document.querySelector('meta[name="citation_title"]');
    if (titleMeta) metadata.title = titleMeta.getAttribute('content');

    const doiMeta = document.querySelector('meta[name="citation_doi"]');
    if (doiMeta) metadata.doi = doiMeta.getAttribute('content');

    const authorMetas = document.querySelectorAll('meta[name="citation_author"]');
    if (authorMetas.length > 0) {
        let authors = [];
        authorMetas.forEach(meta => authors.push(meta.getAttribute('content')));
        metadata.authors = authors.join('; ');
    }

    // 2. Fallback to regex for DOI if not found in meta tags
    if (!metadata.doi) {
        const text = document.body.innerText;
        // Basic DOI regex: 10.\d{4,9}/[-._;()/:A-Z0-9]+
        const doiRegex = /10\.\d{4,9}\/[-._;()/:a-zA-Z0-9]+/i;
        const match = text.match(doiRegex);
        if (match) {
            metadata.doi = match[0];
        }
    }
    
    // Fallback for title
    if (!metadata.title) {
        metadata.title = document.title;
    }

    return metadata;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "extract_metadata") {
        sendResponse(extractMetadata());
    }
    return true;
});
