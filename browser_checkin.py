"""Use the official page to check in; stop if interactive verification is required."""
import logging
import os
import re
import sys
import time
from urllib.parse import urlsplit

logger = logging.getLogger("glados-browser")
ORIGIN = "https://glados.cloud"
TOKEN_READY = """() => {
    try { if (window.turnstile && window.turnstile.getResponse()) return true; } catch (_) {}
    return [...document.querySelectorAll('input[name="cf-turnstile-response"]')]
        .some(node => node.value.length > 0);
}"""


def session_cookies(raw):
    cookies = []
    for part in raw.strip().split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name in ("gld:sess", "gld:sess.sig") and value:
            cookies.append({"name": name, "value": value, "url": ORIGIN,
                            "httpOnly": True})
    if {c["name"] for c in cookies} != {"gld:sess", "gld:sess.sig"} or len(cookies) != 2:
        raise ValueError("COOKIES 必须包含唯一一组 gld:sess 和 gld:sess.sig")
    return cookies


def verify_identity(status, expected):
    data = status.get("data") or {}
    actual = data.get("email", "").strip().lower()
    if status.get("code") != 0 or not actual or actual != expected.strip().lower():
        raise ValueError("当前会话与指定签到邮箱不一致或已失效，停止签到")
    return data


def accepted_result(result):
    code = result.get("code")
    message = str(result.get("message", ""))
    if "verification failed" in message.lower() or "automated check-in detected" in message.lower():
        return False
    return code in (0, 1)


def already_recorded(button_text):
    return bool(re.search(r"got\s+\d+\s+points?", button_text, re.I))


def activate_verification_checkbox(page):
    """Use the named, enabled verification checkbox in Cloudflare's own frame."""
    for frame in page.frames:
        if urlsplit(frame.url).hostname != "challenges.cloudflare.com":
            continue
        client = None
        try:
            client = page.context.new_cdp_session(frame)
            nodes = client.send("Accessibility.getFullAXTree")["nodes"]
            for node in nodes:
                if node.get("role", {}).get("value") != "checkbox":
                    continue
                label = node.get("name", {}).get("value", "").lower()
                if not any(word in label for word in ("human", "verify", "真人", "验证")):
                    continue
                properties = {p["name"]: p.get("value", {}).get("value") for p in node.get("properties", [])}
                if properties.get("disabled") or properties.get("checked") in (True, "true"):
                    continue
                target = node.get("backendDOMNodeId")
                if target:
                    client.send("DOM.focus", {"backendNodeId": target})
                    page.keyboard.press("Space")
                    logger.info("已操作官网 Cloudflare 标准验证框")
                    return True
        except Exception:
            continue
        finally:
            if client:
                client.detach()
    return False


def main():
    try:
        from patchright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    except ImportError:
        if os.getenv("GITHUB_REF_NAME") != "codex/gmail-browser-checkin-20261118":
            raise
        # Temporary probe only; final runtime installation belongs in the workflow.
        import subprocess
        os.environ.setdefault("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", "ubuntu24.04-x64")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "patchright==1.60.1"])
        subprocess.check_call([sys.executable, "-m", "patchright", "install", "chromium"])
        from patchright.sync_api import sync_playwright, TimeoutError as BrowserTimeout

    expected = os.getenv("GLADOS_EXPECTED_EMAIL", "").strip()
    if not expected:
        logger.error("缺少 GLADOS_EXPECTED_EMAIL，无法确认签到账号")
        return 1
    cookies = session_cookies(os.getenv("COOKIES", ""))
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=False)
        try:
            context = browser.new_context(locale="en-US")
            context.add_cookies(cookies)
            page = context.new_page()
            codes = set()
            def record_console(message):
                codes.update(re.findall(r"Turnstile\][^\d]{0,40}(\d{6})", message.text))
            page.on("console", record_console)
            response = context.request.get(ORIGIN + "/api/user/status", timeout=30000)
            if not response.ok:
                raise ValueError("账号查询失败 HTTP %s" % response.status)
            data = verify_identity(response.json(), expected)
            logger.info("已确认指定 Gmail 账号登录，剩余天数=%s", data.get("leftDays", "-"))
            with page.expect_event("requestfinished", predicate=lambda r:
                    urlsplit(r.url).path == "/api/user/checkin/challenge" and r.method == "GET",
                    timeout=60000) as loaded:
                page.goto(ORIGIN + "/console/checkin", wait_until="domcontentloaded", timeout=60000)
            challenge = loaded.value.response().json()
            if challenge.get("code") != 0 or not challenge.get("nonce"):
                logger.error("官网 challenge 加载失败，未提交签到")
                return 1
            required = bool(challenge.get("turnstile"))
            logger.info("官网 challenge 已加载，Turnstile required=%s", required)
            button = page.get_by_role("button", name=re.compile("checkin", re.I)).first
            button.wait_for(state="visible", timeout=45000)
            if already_recorded(button.inner_text()):
                logger.info("今日已签到（官网已显示获得积分）")
                return 0
            button.scroll_into_view_if_needed()
            if required:
                deadline = time.monotonic() + 60
                interacted = False
                while time.monotonic() < deadline and not page.evaluate(TOKEN_READY):
                    if not interacted:
                        interacted = activate_verification_checkbox(page)
                    page.wait_for_timeout(500)
                if not page.evaluate(TOKEN_READY):
                    logger.error("Cloudflare 未完成自动验证，未提交签到。组件错误码=%s", sorted(codes))
                    return 1
                logger.info("官网已完成 Cloudflare 验证")
            try:
                with page.expect_response(
                    lambda r: urlsplit(r.url).path == "/api/user/checkin" and r.request.method == "POST",
                    timeout=90000,
                ) as pending:
                    button.click(timeout=15000)
                result = pending.value.json()
            except BrowserTimeout:
                logger.error("官网未完成签到响应；可能需要人工验证或页面已变化。未点击验证码、未重放签到。")
                return 1
            logger.info("签到响应 code=%s message=%s", result.get("code"), result.get("message", ""))
            if not accepted_result(result):
                logger.error("官网签到未成功；若要求人工 Cloudflare 验证，请在浏览器完成。")
                return 1
            logger.info("签到成功" if result.get("code") == 0 else "今日已签到")
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        sys.exit(main())
    except Exception as exc:
        # Browser errors may embed request details; keep credentials out of logs.
        logger.error("浏览器签到停止 (%s)", type(exc).__name__)
        sys.exit(1)
