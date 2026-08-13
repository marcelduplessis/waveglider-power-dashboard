#!/bin/bash
#
# run_pipeline.sh - Run the complete waveglider power analysis pipeline
#
# Usage:
#   ./run_pipeline.sh
#
# This script runs:
#   1. extract_amps_ports_full_wg1169.py
#   2. extract_amps_ports_full_wg1170.py
#   3. power_analysis.py
#
# Exit codes:
#   0 = success
#   1 = error (see output for details)
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "Waveglider Power Analysis Pipeline"
echo "=========================================="
echo "Working directory: $SCRIPT_DIR"
echo ""

# Run the Python orchestration script
/opt/anaconda3/bin/python3 "$SCRIPT_DIR/run_full_pipeline.py"
exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "Pipeline completed successfully!"
    echo "=========================================="
    exit 0
else
    echo ""
    echo "=========================================="
    echo "Pipeline failed with exit code: $exit_code"
    echo "=========================================="
    exit $exit_code
fi
