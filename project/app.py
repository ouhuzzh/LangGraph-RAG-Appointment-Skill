import sys
import os
import logging

sys.path.insert(0, os.path.dirname(__file__))

# Suppress OTel "Failed to detach context" warning caused by generator/context interaction.
# Tracing is unaffected.
# Known bug: https://github.com/open-telemetry/opentelemetry-python/issues/2606
class _SuppressOtelDetachWarning(logging.Filter):
    def filter(self, record):
        return "Failed to detach context" not in record.getMessage()

logging.getLogger("opentelemetry.context").addFilter(_SuppressOtelDetachWarning())

from ui.gradio_app import create_gradio_ui

if __name__ == "__main__":
    print("\nCreating RAG Assistant...")
    demo = create_gradio_ui()
    print("\nLaunching RAG Assistant...")
    demo.launch(show_error=True)
