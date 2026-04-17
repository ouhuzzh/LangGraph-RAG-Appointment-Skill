import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import config
from core.document_manager import DocumentManager
from core.medical_source_ingest import MedlinePlusXmlImporter
from core.rag_system import RAGSystem


def build_parser():
    parser = argparse.ArgumentParser(description="Import official medical documents into the local knowledge base.")
    parser.add_argument("--source", default="medlineplus", choices=["medlineplus"], help="Official source to import.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of documents to import.")
    parser.add_argument("--output-dir", default=config.MARKDOWN_DIR, help="Directory to write Markdown documents into.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing Markdown documents.")
    parser.add_argument("--index", action="store_true", help="Index imported Markdown documents into PostgreSQL immediately.")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.source != "medlineplus":
        raise ValueError(f"Unsupported source: {args.source}")

    importer = MedlinePlusXmlImporter()
    result = importer.import_latest(
        output_dir=args.output_dir,
        limit=args.limit,
        overwrite=args.overwrite,
    )

    print(
        f"Imported {result.written} Markdown files "
        f"(downloaded={result.downloaded}, skipped={result.skipped}) "
        f"from {result.discovered_url}"
    )

    if args.index:
        rag_system = RAGSystem()
        rag_system.initialize()
        doc_manager = DocumentManager(rag_system)
        index_result = doc_manager.index_existing_markdowns(skip_existing=True)
        rag_system.refresh_knowledge_base_status()
        print(
            "Indexed Markdown files into the knowledge base: "
            f"processed={index_result['processed']}, added={index_result['added']}, skipped={index_result['skipped']}"
        )


if __name__ == "__main__":
    main()
