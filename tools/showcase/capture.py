"""Verify the static product UI with no API server, and capture its actual screens.

Usage: python -m tools.showcase.capture [--no-media]
Only the isolated localhost HTTP server created here is stopped by this tool.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist/showcase"
MEDIA = ROOT / "assets/showcase"


def capture(media: bool) -> None:
    if not (DIST / "web/index.html").is_file():
        raise RuntimeError("Build with npm run --prefix frontend build:showcase first")
    MEDIA.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(DIST))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    frames: list[bytes] = []
    evidence = {
        "screens": [],
        "viewport": [1440, 1100],
        "api_backend": False,
        "data_kind": "synthetic",
        "snapshot_sha256": hashlib.sha256(
            (DIST / "web/scenario/responses.json").read_bytes()
        ).hexdigest(),
        "bundle_manifest_sha256": hashlib.sha256(
            (DIST / "web/asset-manifest.json").read_bytes()
        ).hexdigest(),
    }
    try:
        with (
            tempfile.TemporaryDirectory(prefix="phm-showcase-video-") as video,
            sync_playwright() as runtime,
        ):
            browser = runtime.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1440, "height": 1100},
                locale="ko-KR",
                reduced_motion="reduce",
                **(
                    {
                        "record_video_dir": video,
                        "record_video_size": {"width": 1440, "height": 1100},
                    }
                    if media
                    else {}
                ),
            )
            page = context.new_page()
            page.add_init_script(
                "window.addEventListener('showcase-unavailable',e=>"
                "console.warn('Missing showcase selection: '+e.detail))"
            )
            page.on(
                "console",
                lambda m: print(m.text, flush=True) if "Missing showcase" in m.text else None,
            )
            errors: list[str] = []
            api_network: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: api_network.append(request.url) if "/api/" in request.url else None,
            )

            def shot(name: str) -> None:
                expect(page.get_by_role("complementary", name="제품 체험 안내")).to_be_visible()
                expect(page.locator(".guide .unavailable")).to_have_count(0)
                if name != "01-observe":
                    panel = {
                        "02-signals": "측정 신호",
                        "03-anomaly": "기준 구간 이탈",
                        "04-compare": "두 기간 비교",
                        "05-outlook": "기준 도달 전망",
                        "06-review": "고른 검토 항목",
                    }[name]
                    page.get_by_role("region", name=panel, exact=True).scroll_into_view_if_needed()
                page.screenshot(path=str(MEDIA / (name + ".png"))) if media else None
                evidence["screens"].append({"name": name, "path": page.url.split(origin)[1]})
                if media:
                    # A short pause records the real UI. GIF frames are unaltered captures.
                    for _ in range(8):
                        frames.append(page.screenshot())
                        page.wait_for_timeout(250)

            page.goto(origin + "/web/", wait_until="networkidle")
            expect(
                page.locator("a.row").filter(has_text="순환 펌프 2호기 · 변화 기록")
            ).to_be_visible()
            shot("01-observe")
            page.get_by_role("navigation", name="체험 순서").get_by_role(
                "link", name="2. 신호"
            ).click()
            expect(page.locator(".explorer svg").first).to_be_visible()
            shot("02-signals")
            page.get_by_role("navigation", name="체험 순서").get_by_role(
                "link", name="3. 이상 탐지"
            ).click()
            departures = page.get_by_role("region", name="기준 구간 이탈", exact=True)
            expect(departures.get_by_role("img")).to_be_visible()
            expect(departures.locator(".intervals li")).not_to_have_count(0)
            expect(
                page.get_by_role("heading", name="순환 펌프 2호기 · 변화 기록", exact=True)
            ).to_be_visible()
            shot("03-anomaly")
            page.get_by_role("navigation", name="체험 순서").get_by_role(
                "link", name="4. 비교"
            ).click()
            expect(
                page.get_by_role("region", name="두 기간 비교").get_by_role("table").first
            ).to_be_visible()
            shot("04-compare")
            page.get_by_role("navigation", name="체험 순서").get_by_role(
                "link", name="5. 추세 예측·RUL"
            ).click()
            page.get_by_role("button", name="계산하기", exact=True).click()
            expect(
                page.get_by_role("region", name="기준 도달 전망").get_by_role("img").first
            ).to_be_visible()
            expect(
                page.get_by_text("조건부 잔여수명(RUL) · 종료 기준 15 A", exact=True)
            ).to_be_visible()
            shot("05-outlook")
            outlook_url = page.url
            page.get_by_role("navigation", name="체험 순서").get_by_role(
                "link", name="6. 검토"
            ).click()
            queue = page.get_by_role("region", name="검토함")
            queue.get_by_role("link").first.click()
            expect(page.get_by_role("region", name="고른 검토 항목")).to_contain_text(
                "시연용 검토 메모"
            )
            shot("06-review")
            review_url = page.url
            # Finish the demonstration recording before negative and mobile checks.
            recording = page.video
            page.close()
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda r: api_network.append(r.url) if "/api/" in r.url else None)
            page.goto(outlook_url, wait_until="networkidle")
            page.get_by_role("button", name="계산하기", exact=True).click()
            plot = page.get_by_role("region", name="기준 도달 전망").get_by_role("img")
            expect(plot.first).to_be_visible()
            page.get_by_label("관리 기준 (선택)").fill("14")
            expect(plot).to_have_count(0)
            page.get_by_role("button", name="계산하기", exact=True).click()
            expect(page.locator(".guide .unavailable")).to_be_visible()
            expect(plot).to_have_count(0)
            page.get_by_role("link", name="현재 체험 단계 다시 열기").click()
            expect(page.locator(".guide .unavailable")).to_have_count(0)
            page.get_by_role("button", name="계산하기", exact=True).click()
            expect(plot.first).to_be_visible()
            denied = page.evaluate("""async()=>({
              write:(await fetch('/api/v1/reviews/action',{method:'POST',body:'{}'})).status,
              unknown:(await fetch('/api/v1/outlook?asset_id=other')).status})""")
            assert denied == {"write": 403, "unknown": 404}, denied
            page.goto(review_url, wait_until="networkidle")
            page.reload(wait_until="networkidle")
            expect(page.get_by_role("region", name="고른 검토 항목")).to_contain_text(
                "시연용 검토 메모"
            )
            # Verify the same stored measurements on a narrow viewport and after reload.
            page.set_viewport_size({"width": 390, "height": 900})
            page.goto(
                origin + "/web/?page=assets&tab=signals&monitor_asset=demo-pump-change"
                "&monitor_channel=temperature_c&monitor_range=24h&monitor_anchor=latest",
                wait_until="networkidle",
            )
            expect(page.locator(".explorer svg").first).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            assert not errors and not api_network, (errors, api_network)
            context.close()
            if media and recording:
                recording.save_as(str(MEDIA / "walkthrough.webm"))
                from PIL import Image

                images = [
                    Image.open(BytesIO(raw))
                    .resize((960, 733))
                    .convert("P", palette=Image.Palette.ADAPTIVE)
                    for raw in frames
                ]
                images[0].save(
                    MEDIA / "walkthrough.gif",
                    save_all=True,
                    append_images=images[1:],
                    duration=350,
                    loop=0,
                    optimize=True,
                )
                evidence.update(review_url=review_url.split(origin)[1], browser=browser.version)
                (MEDIA / "capture.json").write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
                )
            browser.close()
        print("PASS: static current UI, captured calculations, read-only guards, reload and mobile")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-media", action="store_true")
    capture(not parser.parse_args().no_media)
