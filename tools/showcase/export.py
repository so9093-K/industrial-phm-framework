"""Export exact, real read API responses for the finite static product walkthrough.

Usage: python -m tools.showcase.export
The temporary workspace is separate from every Operations workspace. The browser
visits the real UI, so its exact queries (including default selections) are captured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qsl, urlencode, urlsplit

from playwright.sync_api import expect, sync_playwright

from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tools.showcase.prepare import prepare

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "examples/operations/showcase"


def key(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(sorted(parse_qsl(parts.query)), safe="*").replace("~", "%7E")
    return parts.path + ("?" + query if query else "")


def export(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phm-showcase-export-") as temporary:
        root = Path(temporary) / "workspace"
        manifest = prepare(root)
        server = create_operations_web_read_server(root)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        responses: dict[str, object] = {}
        try:
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch()
                page = browser.new_page(locale="ko-KR", viewport={"width": 1440, "height": 1050})

                def record(response):
                    if "/api/" not in response.url:
                        return
                    body = response.json()
                    if urlsplit(response.url).path == "/api/v1/session":
                        body["csrf_token"] = None
                    responses[key(response.url)] = {"status": response.status, "body": body}

                requested: set[str] = set()
                page.on(
                    "request",
                    lambda r: (
                        requested.add(r.url) if "/api/" in r.url and r.method == "GET" else None
                    ),
                )

                def visit(query: str) -> None:
                    page.goto(origin + "/web/" + query, wait_until="networkidle")
                    print("Exported selection:", query or "monitor", flush=True)

                def calculate() -> None:
                    with (
                        page.expect_response(
                            lambda r: urlsplit(r.url).path == "/api/v1/forecast", timeout=60_000
                        ) as forecast,
                        page.expect_response(
                            lambda r: urlsplit(r.url).path == "/api/v1/outlook", timeout=60_000
                        ) as outlook,
                    ):
                        page.get_by_role("button", name="계산하기", exact=True).click()
                    for response in (forecast.value, outlook.value):
                        assert response.status == 200, response.text()
                        record(response)
                    expect(
                        page.get_by_role("region", name="기준 도달 전망").get_by_role("img").first
                    ).to_be_visible()
                    expect(
                        page.get_by_text("아직 이 결과에 대한 해설이 없습니다.", exact=True)
                    ).to_be_visible(timeout=60_000)
                    page.wait_for_load_state("networkidle")

                visit("")
                for asset in ("demo-pump-change", "demo-pump-stable"):
                    base = f"?page=assets&monitor_asset={asset}"
                    visit(base)
                    for channel in ("current_a", "temperature_c"):
                        chosen = base + f"&monitor_channel={channel}"
                        for span in ("15m", "1h", "24h", "7d"):
                            visit(
                                chosen + f"&tab=signals&monitor_range={span}&monitor_anchor=latest"
                            )
                        for baseline in ("first-30", "first-50", "all"):
                            visit(
                                chosen
                                + f"&tab=anomaly&method=baseline&departure_baseline={baseline}"
                            )
                        visit(chosen + "&tab=change&method=compare&data=history")
                        visit(chosen + "&tab=change&method=relation&data=history")
                        # Default history forecast and guided 13/15 A example. Both
                        # calculations reach Prophet and the server's provenance checks.
                        visit(chosen + "&tab=outlook&data=history")
                        calculate()
                    if asset == "demo-pump-change":
                        visit(
                            base + "&tab=outlook&data=history&monitor_channel=current_a"
                            "&projection_horizon=1h&projection_management=13&projection_end=15"
                            "&forecast_seasonality=off"
                        )
                        calculate()
                    visit(f"?page=investigations&monitor_asset={asset}")
                    visit(f"?page=maintenance&monitor_asset={asset}")
                review = manifest["review"]
                assert isinstance(review, dict)
                visit(
                    "?page=maintenance&monitor_asset=demo-pump-change&finding_id="
                    + str(review["finding_id"])
                )
                expect(page.get_by_role("region", name="고른 검토 항목")).to_contain_text(
                    "시연용 검토 메모"
                )
                visit("?page=system")
                visit("?page=system&section=status")
                # A navigation may cancel polling or a lazy panel read. Re-read its
                # exact GET on the still-running real server; never invent a body.
                for url in sorted(requested):
                    if key(url) not in responses:
                        record(page.request.get(url))
                page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
        # Input CSVs and real response bodies travel together. Never export a token.
        for source in (root / "inputs").glob("*.csv"):
            (output / source.name).write_bytes(source.read_bytes())
        manifest["generated_from_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        manifest["generator"] = "tools/showcase/prepare.py"
        manifest["generator_sha256"] = hashlib.sha256(
            (ROOT / "tools/showcase/prepare.py").read_bytes()
        ).hexdigest()
        manifest["revision_is_base_commit"] = True
        manifest["response_count"] = len(responses)
        manifest["review_url"] = (
            "/web/?page=maintenance&monitor_asset=demo-pump-change&finding_id="
            + str(review["finding_id"])
        )
        (output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        (output / "responses.json").write_text(
            json.dumps(
                {"schema_version": 1, "responses": responses},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )
        print(f"Exported {len(responses)} actual API responses and two input CSVs to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    export(parser.parse_args().output)
