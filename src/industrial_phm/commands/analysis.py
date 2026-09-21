"""Analysis command handlers."""

from __future__ import annotations

import argparse
import sys

from industrial_phm.analysis import (
    AnalysisReportError,
    AnalysisViewError,
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
    write_analysis_report_markdown,
)


def _run_analysis_report(args: argparse.Namespace) -> int:
    try:
        analysis = load_xjtu_lstm_analysis_view(args.anomaly)
        prognostics = (
            None if args.prognostics is None else load_xjtu_rul_analysis_view(args.prognostics)
        )
        write_analysis_report_markdown(
            analysis,
            args.asset,
            args.output,
            prognostics=prognostics,
        )
    except (OSError, AnalysisReportError, AnalysisViewError) as error:
        print(f"analysis report failed: {error}", file=sys.stderr)
        return 1

    print(f"asset: {args.asset}")
    print(f"anomaly artifact: {args.anomaly}")
    if args.prognostics is not None:
        print(f"attached prognostics artifact: {args.prognostics}")
    print(f"report: {args.output}")
    return 0

