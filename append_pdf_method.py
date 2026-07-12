import re

with open("main.py", "r") as f:
    content = f.read()

method = """
    def _download_oa_pdfs(self):
        if self._dataframe is None or self._dataframe.empty:
            return
            
        oa_records = self._dataframe[self._dataframe.get("is_oa", False) == True].to_dict('records')
        if not oa_records:
            messagebox.showinfo("PDFs", "Nenhum documento Open Access encontrado no corpus.")
            return
            
        import threading
        import urllib.request
        import urllib.error
        import os
        import re
        
        # Determine project name for folder
        proj_name = "Projeto_Sem_Nome"
        if getattr(self, "_current_tab_key", "") == "projects":
            # Can't reliably get current from tab, fallback to a timestamp or default
            pass
            
        import time
        proj_name = f"projeto_{int(time.time())}"
        out_dir = os.path.expanduser(f"~/Blicsa/pdfs/{proj_name}")
        os.makedirs(out_dir, exist_ok=True)
        
        self._pdf_cancel_event = threading.Event()
        
        def slugify(value):
            value = str(value).lower().strip()
            value = re.sub(r'[^\w\s-]', '', value)
            value = re.sub(r'[-\s]+', '-', value)
            return value[:50]
            
        def worker():
            downloaded = 0
            failed = 0
            
            for i, r in enumerate(oa_records):
                if self._pdf_cancel_event.is_set():
                    break
                    
                self.after(0, self._set_busy, f"Baixando PDF {i+1}/{len(oa_records)}...")
                
                url = r.get("oa_url")
                if not url:
                    failed += 1
                    continue
                    
                authors = str(r.get("authors", "Autor"))
                first_author = authors.split(";")[0].split(",")[0].strip()
                first_author = slugify(first_author)
                
                year = str(r.get("year", "0000"))
                title = slugify(r.get("title", "Sem titulo"))
                
                filename = f"{first_author}_{year}_{title}.pdf"
                filepath = os.path.join(out_dir, filename)
                
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as response, open(filepath, 'wb') as out_file:
                        out_file.write(response.read())
                    downloaded += 1
                except Exception:
                    failed += 1
                    
            self.after(0, self._set_idle, f"PDFs baixados. {downloaded} sucessos, {failed} falhas.")
            self.after(0, lambda: messagebox.showinfo("Download Concluído", f"{downloaded} baixados, {failed} falhas.\n\nSalvos em:\n{out_dir}"))
            
        threading.Thread(target=worker, daemon=True).start()
"""

# Append to class Application
content = content.replace("def _build_tab_corpus(self)", method + "\n    def _build_tab_corpus(self)")

with open("main.py", "w") as f:
    f.write(content)
