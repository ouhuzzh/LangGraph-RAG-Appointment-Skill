from pathlib import Path
import shutil
import config
from core.medical_source_ingest import MedlinePlusXmlImporter, NhcPdfWhitelistImporter, WhoHtmlWhitelistImporter
from utils import pdfs_to_markdowns, clear_directory_contents

class DocumentManager:

    def __init__(self, rag_system):
        self.rag_system = rag_system
        self.markdown_dir = Path(config.MARKDOWN_DIR)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)

    def get_markdown_paths(self):
        if not self.markdown_dir.exists():
            return []
        return sorted(self.markdown_dir.glob("*.md"))

    def get_local_document_stats(self):
        markdown_paths = self.get_markdown_paths()
        return {
            "local_markdown_files": len(markdown_paths),
            "local_markdown_names": [path.name for path in markdown_paths],
        }

    def _index_markdown_paths(self, markdown_paths, progress_callback=None, skip_existing=True):
        markdown_paths = [Path(path) for path in markdown_paths if path]
        if not markdown_paths:
            return {"processed": 0, "added": 0, "skipped": 0}

        self.rag_system.vector_db.create_collection(self.rag_system.collection_name)
        collection = self.rag_system.vector_db.get_collection(self.rag_system.collection_name)
        indexed_document_nos = self.rag_system.vector_db.get_indexed_document_nos() if skip_existing else set()

        added = 0
        skipped = 0
        processed = 0

        for index, md_path in enumerate(markdown_paths):
            if progress_callback:
                progress_callback((index + 1) / len(markdown_paths), f"Processing {md_path.name}")

            processed += 1
            document_no = md_path.stem
            if skip_existing and document_no in indexed_document_nos:
                skipped += 1
                continue

            try:
                parent_chunks, child_chunks = self.rag_system.chunker.create_chunks_single(md_path)
                if not child_chunks:
                    skipped += 1
                    continue

                self.rag_system.parent_store.save_many(parent_chunks)
                collection.add_documents(child_chunks)
                indexed_document_nos.add(document_no)
                added += 1
            except Exception as e:
                print(f"Error processing {md_path}: {e}")
                skipped += 1

        return {"processed": processed, "added": added, "skipped": skipped}

    def index_existing_markdowns(self, progress_callback=None, skip_existing=True):
        return self._index_markdown_paths(
            self.get_markdown_paths(),
            progress_callback=progress_callback,
            skip_existing=skip_existing,
        )

    def add_documents(self, document_paths, progress_callback=None):
        if not document_paths:
            return 0, 0

        document_paths = [document_paths] if isinstance(document_paths, str) else document_paths
        document_paths = [p for p in document_paths if p and Path(p).suffix.lower() in [".pdf", ".md"]]

        if not document_paths:
            return 0, 0

        prepared_markdowns = []
        skipped = 0

        for i, doc_path in enumerate(document_paths):
            if progress_callback:
                progress_callback((i + 1) / len(document_paths), f"Processing {Path(doc_path).name}")

            doc_name = Path(doc_path).stem
            md_path = self.markdown_dir / f"{doc_name}.md"

            try:
                if Path(doc_path).suffix.lower() == ".md":
                    if not md_path.exists():
                        shutil.copy(doc_path, md_path)
                else:
                    pdfs_to_markdowns(str(doc_path), overwrite=False)
                prepared_markdowns.append(md_path)
            except Exception as e:
                print(f"Error processing {doc_path}: {e}")
                skipped += 1

        result = self._index_markdown_paths(
            prepared_markdowns,
            progress_callback=progress_callback,
            skip_existing=True,
        )
        return result["added"], skipped + result["skipped"]

    def get_markdown_files(self):
        return sorted([p.name.replace(".md", ".pdf") for p in self.get_markdown_paths()])

    def clear_all(self):
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(self.markdown_dir)

        self.rag_system.vector_db.delete_collection(self.rag_system.collection_name)
        self.rag_system.parent_store.clear_store()
        self.rag_system.vector_db.create_collection(self.rag_system.collection_name)

    def import_official_source(self, source: str, limit: int = 10, overwrite: bool = False, index_after_import: bool = True):
        importers = {
            "medlineplus": MedlinePlusXmlImporter,
            "nhc": NhcPdfWhitelistImporter,
            "who": WhoHtmlWhitelistImporter,
        }
        if source not in importers:
            raise ValueError(f"Unsupported official source: {source}")

        importer = importers[source]()
        if source == "medlineplus":
            result = importer.import_latest(self.markdown_dir, limit=limit, overwrite=overwrite)
        else:
            result = importer.import_whitelist(self.markdown_dir, limit=limit, overwrite=overwrite)

        index_result = {"processed": 0, "added": 0, "skipped": 0}
        if index_after_import:
            index_result = self.index_existing_markdowns(skip_existing=True)
            self.rag_system.refresh_knowledge_base_status()

        return result, index_result
