"""
One-shot diagnostic: fetch a known profile page through Playwright + our proxy
and print what we actually get back. Helps pinpoint why expand.py is failing.

Run: python test_profile.py [username]
"""
import asyncio, os, re, sys, json
from dotenv import load_dotenv
from TikTokApi import TikTokApi

load_dotenv()

MS_TOKENS = [t.strip() for t in os.getenv("MS_TOKEN", "").split(",") if t.strip()]
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USER = os.getenv("PROXY_USER", "").strip()
PROXY_PASS = os.getenv("PROXY_PASS", "").strip()


def _build_proxy_spec():
    if not PROXY_SERVER:
        return None
    user, password = PROXY_USER, PROXY_PASS
    import time as _t
    sticky = f"session-diag{int(_t.time())%100000}"
    if "session-" in password:
        password = re.sub(r"session-[a-zA-Z0-9]+", sticky, password)
    elif "session-" in user:
        user = re.sub(r"session-[a-zA-Z0-9]+", sticky, user)
    return {"server": PROXY_SERVER, "username": user, "password": password}


async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "therock"
    print(f"Testing profile: @{username}")

    api = TikTokApi()
    await api.__aenter__()
    try:
        kwargs = dict(
            ms_tokens=MS_TOKENS[:1] if MS_TOKENS else None,
            num_sessions=1, sleep_after=3, headless=True,
            browser=os.getenv("TIKTOK_BROWSER", "webkit"),
            timeout=90000,
            suppress_resource_load_types=["image", "media", "font", "stylesheet"],
        )
        proxy_spec = _build_proxy_spec()
        if proxy_spec:
            kwargs["proxies"] = [proxy_spec]
        await api.create_sessions(**kwargs)
        print(f"Session created. {len(api.sessions)} session(s) active.")

        session = api.sessions[0]
        page = session.page
        url = f"https://www.tiktok.com/@{username}"
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        print(f"Final URL: {page.url}")

        html = await page.content()
        print(f"HTML length: {len(html):,} chars")

        # Key markers
        print(f"\n--- Content probes ---")
        print(f"  __UNIVERSAL_DATA_FOR_REHYDRATION__ present: {'__UNIVERSAL_DATA_FOR_REHYDRATION__' in html}")
        print(f"  Old SIGI_STATE present: {'SIGI_STATE' in html}")
        print(f"  '404' in html: {'/404' in html or '>404<' in html}")
        print(f"  'Couldn' + apostrophe + 't find' present: {'Couldn' in html and 't find' in html}")
        print(f"  'Login' or 'Log in' present: {'Log in' in html}")
        print(f"  'CAPTCHA' or 'verify' present: {'captcha' in html.lower() or 'verify' in html.lower()}")

        # Try to extract __UNIVERSAL_DATA_FOR_REHYDRATION__
        m = re.search(
            r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if m:
            blob = json.loads(m.group(1))
            scope = blob.get("__DEFAULT_SCOPE__", {})
            print(f"\n--- __UNIVERSAL_DATA_FOR_REHYDRATION__ keys in __DEFAULT_SCOPE__ ---")
            for k in scope.keys():
                print(f"  {k}")
            ud = scope.get("webapp.user-detail", {})
            if ud:
                ui = ud.get("userInfo")
                if ui:
                    user = ui.get("user", {})
                    stats = ui.get("stats") or ui.get("statsV2") or {}
                    print(f"\n  ✓ userInfo FOUND")
                    print(f"    secUid:   {user.get('secUid', 'MISSING')[:40]}...")
                    print(f"    uniqueId: {user.get('uniqueId', 'MISSING')}")
                    print(f"    nickname: {user.get('nickname', 'MISSING')}")
                    print(f"    region:   {user.get('region', 'MISSING')}")
                    print(f"    followers: {stats.get('followerCount', 'MISSING')}")
                else:
                    print(f"  ✗ userInfo is None/missing")
                    print(f"    webapp.user-detail keys: {list(ud.keys())}")
            else:
                print(f"\n  ✗ webapp.user-detail NOT in __DEFAULT_SCOPE__")
        else:
            print(f"\n✗ __UNIVERSAL_DATA_FOR_REHYDRATION__ not matched by regex")
            # Dump first 500 chars for inspection
            print(f"\nFirst 800 chars of HTML:\n{html[:800]}")

        # Save full HTML for inspection
        with open("/tmp/profile_test.html", "w") as f:
            f.write(html)
        print(f"\nFull HTML saved to /tmp/profile_test.html")

    finally:
        await api.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
