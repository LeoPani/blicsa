# BUGREPORT

1. **Filters do not appear after a search completes:**
   - **Root cause:** The filter sidebar was never implemented for the search results screen; the search flow previously just dumped results directly into the corpus without a review screen or post-search filtering mechanism.
   
2. **Not all results appear:**
   - **Root cause:** In `core/sources/openalex.py`, the pagination logic checks `count_fetched >= max_results` but breaks early if `cancel_event` is set, or if the API cursor pagination silently drops records due to cursor expiration, or if deduplication silently removes records during `fuzzy_deduplicate_papers` without notifying the user of the dropped count before import.
   
3. **Search jumps straight to the map:**
   - **Root cause:** At the end of `_search_worker` in `main.py`, there is an explicit call to `self.after(0, lambda: self._switch_tab("viz"))` which unconditionally jumps to the map visualization tab immediately after fetching and merging results.
