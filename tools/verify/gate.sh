#!/bin/sh
# The single owner of the verification commands. CI workflow steps and `make verify-linux`
# both call these stages, so a local Linux run repeats exactly what CI checks.
#
#   sh tools/verify/gate.sh <stage> [<stage> ...]
#
# Composite stages: source, web-next, forecast, ci (all three workflows), full (every test).
set -eu
cd "$(dirname "$0")/../.."
. tools/verify/versions.env

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}
locked() {
  run uv run --locked --extra operations "$@"
}
# Browser tests run in the environment the browser-runtime stage extended with Playwright.
browser() {
  run uv run --no-sync "$@"
}

WEB_NEXT_PYTHON="
tests/integration/test_operations_web_next_static.py
tests/integration/test_operations_web_explore.py
tests/integration/test_operations_web_phm.py
tests/integration/test_operations_web_outlook_briefing.py
tests/integration/test_operations_web_review.py
tests/integration/test_operations_web_phm_explanation.py
"
WEB_NEXT_BROWSER="
tests/acceptance/test_operations_web_next_browser.py
tests/acceptance/test_operations_web_next_signal_browser.py
tests/acceptance/test_operations_web_next_departures_browser.py
tests/acceptance/test_operations_web_next_compare_browser.py
tests/acceptance/test_operations_web_next_projection_browser.py
tests/acceptance/test_operations_web_next_briefings_browser.py
tests/acceptance/test_operations_web_next_acquisition_outlook_browser.py
tests/acceptance/test_operations_web_next_relation_browser.py
tests/acceptance/test_operations_web_next_review_browser.py
tests/acceptance/test_operations_web_next_spectrum_browser.py
tests/acceptance/test_operations_web_next_acquisition_profile_browser.py
tests/acceptance/test_operations_web_next_acquisition_relation_browser.py
tests/acceptance/test_operations_web_next_model_evidence_browser.py
tests/acceptance/test_operations_web_next_outlook_capture_browser.py
tests/acceptance/test_operations_web_next_finding_review_browser.py
tests/acceptance/test_operations_web_next_model_explanation_browser.py
tests/acceptance/test_operations_web_next_investigations_browser.py
tests/acceptance/test_operations_web_next_operations_browser.py
tests/acceptance/test_operations_web_next_connections_browser.py
tests/acceptance/test_operations_web_next_registration_browser.py
tests/acceptance/test_operations_web_next_model_connect_browser.py
tests/acceptance/test_operations_web_next_score_trend_browser.py
tests/acceptance/test_operations_web_next_monitor_attention_browser.py
tests/acceptance/test_operations_web_next_electrical_condition_browser.py
"
FORECAST_PYTHON="
tests/integration/test_operations_web_forecast.py
tests/integration/test_operations_web_outlook.py
tests/unit/test_condition_outlook.py
tests/integration/test_operations_web_outlook_briefing.py
tests/unit/test_outlook_answer.py
"
FORECAST_BROWSER="
tests/acceptance/test_operations_forecast_browser.py
tests/acceptance/test_operations_outlook_browser.py
tests/acceptance/test_operations_phm_browser.py
tests/acceptance/test_operations_phm_connect_browser.py
tests/acceptance/test_operations_phm_monitor_browser.py
tests/acceptance/test_operations_electrical_phm_browser.py
tests/acceptance/test_operations_signal_explore_browser.py
tests/acceptance/test_operations_stored_monitor_browser.py
"

stage() {
  case "$1" in
    # CI: source checks
    lock) run uv lock --check ;;
    lint) locked ruff check . ;;
    format) locked ruff format --check . ;;
    types) locked mypy ;;
    unit) locked pytest tests/unit tests/contract ;;
    # Web-next foundation
    frontend-install) run npm ci --prefix frontend --no-audit --no-fund ;;
    frontend-check) run npm run --prefix frontend check ;;
    frontend-test) run npm test --prefix frontend ;;
    frontend-build) run npm run --prefix frontend build ;;
    manifest) locked python tools/verify/check_web_next_package.py manifest ;;
    web-next-python) locked pytest $WEB_NEXT_PYTHON ;;
    wheel)
      rm -f dist/*.whl
      run uv build --wheel
      locked python tools/verify/check_web_next_package.py wheel
      ;;
    browser-runtime)
      locked python -c "pass"
      run uv pip install --python .venv/bin/python "playwright==$PLAYWRIGHT_VERSION"
      # CI runners need system libraries; the verification image already has them.
      if [ "${PLAYWRIGHT_SYSTEM_DEPS:-install}" = install ]; then
        browser python -m playwright install --with-deps chromium
      else
        browser python -m playwright install chromium
      fi
      ;;
    web-next-browser) browser pytest $WEB_NEXT_BROWSER ;;
    # Forecast acceptance
    forecast-python) locked pytest $FORECAST_PYTHON ;;
    forecast-browser) browser pytest $FORECAST_BROWSER ;;
    # Composites mirror one workflow each.
    source) for name in lock lint format types unit; do stage "$name"; done ;;
    web-next)
      for name in frontend-install frontend-check frontend-test frontend-build manifest \
        web-next-python wheel browser-runtime web-next-browser; do
        stage "$name"
      done
      ;;
    forecast)
      for name in forecast-python browser-runtime forecast-browser; do stage "$name"; done
      ;;
    ci) for name in source web-next forecast; do stage "$name"; done ;;
    # Every test, including layers no workflow selects yet. Not a CI gate.
    full)
      for name in frontend-install frontend-build browser-runtime; do stage "$name"; done
      browser pytest tests
      ;;
    *)
      echo "unknown verification stage: $1" >&2
      exit 2
      ;;
  esac
}

[ "$#" -gt 0 ] || set -- ci
for requested in "$@"; do
  stage "$requested"
done
