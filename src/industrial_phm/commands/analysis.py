"""Analysis command handlers."""

from __future__ import annotations

import argparse
import sys

from industrial_phm.analysis import (
    AnalysisReportError,
    AnalysisViewError,
    write_analysis_report_markdown,
)
from industrial_phm.analysis.loader import load_analysis_view


def _run_analysis_report(args: argparse.Namespace) -> int:
    try:
        analysis = load_analysis_view(args.anomaly)
        write_analysis_report_markdown(analysis, args.asset, args.output)
    except (OSError, AnalysisReportError, AnalysisViewError) as error:
        print(f"analysis report failed: {error}", file=sys.stderr)
        return 1

    print(f"asset: {args.asset}")
    print(f"anomaly artifact: {args.anomaly}")
    print(f"report: {args.output}")
    return 0
