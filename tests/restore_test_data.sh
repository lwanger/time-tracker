#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Restoring test data from backups..."
cp "$SCRIPT_DIR/bak/clients.json"                "$SCRIPT_DIR/data/clients.json"
cp "$SCRIPT_DIR/bak/invoices.json"               "$SCRIPT_DIR/data/invoices.json"
cp "$SCRIPT_DIR/bak/time_logs/test_time_log.csv" "$SCRIPT_DIR/data/time_logs/test_time_log.csv"
echo "Done."
