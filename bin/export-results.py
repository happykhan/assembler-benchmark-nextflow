#!/usr/bin/env python3
"""Export a self-contained report and an independently verifiable manifest."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.report import export_results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, nargs='+', required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--expected-slots', type=int, required=True)
    parser.add_argument('--run-id', default='quick')
    parser.add_argument('--plan', type=Path, help='Frozen explicit slots or cases/assemblers plan')
    args = parser.parse_args()
    manifest = export_results(args.results, args.out_dir, args.expected_slots, args.run_id, args.plan)
    print(f"Exported {manifest['result_count']}/{manifest['expected_slots']} slots; complete={manifest['complete']}")
