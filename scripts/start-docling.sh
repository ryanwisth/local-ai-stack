#!/bin/bash
# Docling document-extraction service for Open WebUI (layout-aware PDF/table extraction).
# LOOPBACK ONLY. Without --host, docling-serve listens on every interface; see docs/lessons-learned.md.
source "$(dirname "$0")/env.sh"
exec docling-serve run --host 127.0.0.1 --port "$DOCLING_PORT"
