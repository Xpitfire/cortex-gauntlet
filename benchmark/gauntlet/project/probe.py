"""In-container probe for Track P: serve the candidate app, exercise it, emit result.json.

Runs INSIDE the sandbox container (copied to /probe/probe.py), so it depends only on the stdlib +
optional Playwright — never on the rest of the gauntlet package. The host (sandbox.py) discovers the
launch plan and passes it via env (GAUNTLET_SERVE / GAUNTLET_PORT / GAUNTLET_READY); the probe starts
the server, then:
- REST: discovers the products endpoint (array OR wrapped {products:[...]}) and walks add-to-cart +
  create-order against discovered endpoints with a real product id (best-effort, app's API is its own).
- UI journeys: for each acceptance journey it NAVIGATES (home -> listing -> product -> cart ->
  checkout) and evaluates that journey's declared checks with role/name/DOM assertions — not a
  literal home-page text grep.
- PWA + a11y: manifest link + validity, service-worker registration, responsive overflow at
  390/1280, landmarks, image alt-text, accessible names, and an offline critical-violation heuristic
  (real axe-core needs network we don't have under --network none).
- robustness: unknown route 404s, empty cart doesn't 500, an invalid card is handled gracefully.

Network-bound checks (the live Stripe payment) would need egress (GAUNTLET_EGRESS=1). NOTE: the sandbox
does not currently set that flag under any policy and no test-payment attempt is implemented, so the
payment check is always reported as unverified (excluded from functional — never a guaranteed fail);
the checkout journey is scored structurally (reaching a checkout surface). The REST + robustness
+ readiness logic is HTTP-only and unit-tested against an in-process stub; the Playwright path is
guarded and validated in a browser-enabled container.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# candidate endpoints we probe per contract (structure/route is the harness's choice -> discover)
_PRODUCT_PATHS = ["/api/products", "/products", "/api/catalog", "/catalog",
                  "/api/v1/products", "/catalog.json", "/api/products/"]
_CART_PATHS = ["/api/cart/items", "/api/cart", "/cart/items", "/api/cart/add", "/api/basket/items"]
_ORDER_PATHS = ["/api/checkout", "/api/orders", "/api/order", "/api/payment-intent",
                "/api/payment_intents", "/api/payments", "/checkout"]
# a list of product objects can be bare or wrapped under one of these keys
_LIST_KEYS = ["products", "items", "data", "results", "catalog", "skus"]
# id field a product object might use, in preference order
_ID_KEYS = ["id", "sku", "_id", "productId", "slug", "handle"]
_PRICE_RE = re.compile(r"(?:€|\$|£|EUR|USD|CHF)\s?\d|\d+[.,]\d{2}", re.I)
_TEST_CARD = "4242 4242 4242 4242"


def _get(base: str, path: str, timeout: float = 6.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(base + path, timeout=timeout) as resp:
            return resp.status, resp.read(400_000).decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


def _post(base: str, path: str, payload: dict, timeout: float = 6.0) -> tuple[int, str]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(200_000).decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


def _extract_list(body: str) -> list:
    """Parse a products list from a JSON array OR an object wrapping one (products/items/data/...)."""
    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in _LIST_KEYS:
            if isinstance(obj.get(key), list):
                return obj[key]
    return []


def _product_id(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in _ID_KEYS:
        if item.get(key) not in (None, ""):
            return str(item[key])
    return None


def wait_ready(base: str, ready_path: str = "/", timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _ = _get(base, ready_path, timeout=2.0)
        if 0 < status < 500:
            return True
        time.sleep(0.5)
    return False


def check_rest(base: str, contracts: list[dict]) -> list[dict]:
    """Endpoint discovery + a real state walk: list products, add one to a cart, create an order."""

    results = []
    products_path, sample_id = None, None
    for path in _PRODUCT_PATHS:
        status, body = _get(base, path)
        items = _extract_list(body) if status == 200 else []
        if items:
            products_path, sample_id = path, _product_id(items[0]) or "1"
            break

    cart_ok = False
    if products_path is not None:
        for path in _CART_PATHS:
            for payload in ({"productId": sample_id, "quantity": 1},
                            {"sku": sample_id, "qty": 1, "size": "M"},
                            {"id": sample_id, "quantity": 1, "size": "M"}):
                status, body = _post(base, path, payload)
                if status in (200, 201) and re.search(r"total|subtotal|items|lineItems|count|cart",
                                                       body, re.I):
                    cart_ok = True
                    break
            if cart_ok:
                break

    for c in contracts:
        if c["id"] == "list_products":
            ok = products_path is not None
            detail = f"{products_path} -> list of {len(_extract_list(_get(base, products_path)[1]))}" if ok \
                else "no products endpoint returned a JSON list"
        elif c["id"] == "cart_add":
            ok = cart_ok
            detail = "added to cart" if ok else "no cart endpoint accepted an add (state-dependent)"
        elif c["id"] == "create_order":
            ok = False
            for path in _ORDER_PATHS:
                status, body = _post(base, path, {"email": "t@example.com", "card": _TEST_CARD,
                                                  "items": [{"id": sample_id, "quantity": 1}]})
                if status in (200, 201) and re.search(
                        r"order|clientSecret|payment[_-]?intent|confirmation|id", body, re.I):
                    ok = True
                    break
            detail = "created an order/payment intent" if ok else "no order endpoint accepted a POST"
        else:
            ok, detail = False, "unsupported contract"
        results.append({"id": c["id"], "passed": ok, "detail": detail})
    return results


def check_robustness(base: str, checks: list[dict]) -> list[dict]:
    """HTTP robustness: unknown route 404 (not 500), empty cart serves, bad card handled (no 500)."""

    results = []
    for c in checks:
        if c["id"] == "unknown_route":
            status, _ = _get(base, "/__definitely_not_a_route__")
            results.append({"id": c["id"], "passed": status in (404, 200), "detail": f"status={status}"})
        elif c["id"] == "empty_cart":
            status, _ = _get(base, "/cart")
            ok = status < 500 if status else _get(base, "/api/cart")[0] < 500
            results.append({"id": c["id"], "passed": bool(ok), "detail": f"status={status}"})
        elif c["id"] == "bad_card":  # a declined/invalid card must be handled, never a 500/stacktrace
            statuses = [_post(base, p, {"card": "4000 0000 0000 0002", "items": []})[0]
                        for p in _ORDER_PATHS]
            seen = [s for s in statuses if s]
            ok = bool(seen) and all(s < 500 for s in seen)
            results.append({"id": c["id"], "passed": ok,
                            "detail": f"order statuses={seen or 'no endpoint'}"})
        else:
            results.append({"id": c["id"], "passed": False, "detail": "unverified"})
    return results


# ---- UI: navigate + assert -------------------------------------------------
def _role(page, role: str) -> bool:
    try:
        return page.get_by_role(role).count() > 0
    except Exception:
        return False


def _named(page, pattern: str) -> bool:
    """An interactive element (or any text) with an accessible name matching the regex."""
    rx = re.compile(pattern.replace("(", "").replace(")", ""), re.I)
    for role in ("link", "button", "menuitem"):
        try:
            if page.get_by_role(role, name=rx).count() > 0:
                return True
        except Exception:
            continue
    try:
        return page.get_by_text(rx).count() > 0
    except Exception:
        return False


def _count_cards(page) -> int:
    best = 0
    for sel in ('[data-testid*="product" i]', "article", '[class*="product-card" i]',
                '[class*="product" i]', '[class*="card" i]', "main a:has(img)", "li:has(img)"):
        try:
            best = max(best, page.locator(sel).count())
        except Exception:
            continue
    return best


def _has_price(page) -> bool:
    try:
        return page.get_by_text(_PRICE_RE).count() > 0
    except Exception:
        return False


def _has_search(page) -> bool:
    """A search input, however implemented (role=searchbox, type=search, or a search-named input)."""
    if _role(page, "searchbox"):
        return True
    for sel in ('input[type="search"]', 'input[name*="search" i]', 'input[placeholder*="search" i]',
                'input[placeholder*="such" i]', 'input[aria-label*="search" i]', '[role="search"] input'):
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False


def _has_variant(page) -> bool:
    for sel in ("select", '[role="combobox"]', '[class*="size" i] button', 'button[class*="variant" i]'):
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    try:
        return page.get_by_role("button", name=re.compile(r"^(xs|s|m|l|xl|xxl|\d{2})$", re.I)).count() > 0
    except Exception:
        return False


def _click_first(page, locator) -> bool:
    try:
        if locator.count() > 0:
            locator.first.click(timeout=4000)
            page.wait_for_timeout(700)
            return True
    except Exception:
        pass
    return False


def _open_listing(page, base: str) -> bool:
    try:
        nav = page.get_by_role("navigation")
        if nav.count() and _click_first(page, nav.get_by_role("link")) and _count_cards(page) >= 2:
            return True
    except Exception:
        pass
    if _click_first(page, page.get_by_role(
            "link", name=re.compile(r"shop|products|catalog|all|damen|women|men|herren|kinder", re.I))):
        if _count_cards(page) >= 2:
            return True
    for route in ("/listing", "/products", "/catalog", "/shop", "/c/all", "/category/all"):
        try:
            page.goto(base + route, timeout=8000)
            page.wait_for_timeout(500)
            if _count_cards(page) >= 2:
                return True
        except Exception:
            continue
    return _count_cards(page) >= 2


def _open_pdp(page) -> bool:
    for sel in ("main a:has(img)", "article a", '[class*="product" i] a', "a:has(img)"):
        try:
            if page.locator(sel).count() and _click_first(page, page.locator(sel)):
                return _has_price(page) or _has_variant(page)
        except Exception:
            continue
    return False


def _add_to_cart(page) -> bool:
    rx = re.compile(r"add to cart|in den warenkorb|add to bag|add to basket", re.I)
    return _click_first(page, page.get_by_role("button", name=rx)) or _click_first(
        page, page.get_by_role("link", name=rx))


def _open_cart(page, base: str) -> bool:
    rx = re.compile(r"cart|warenkorb|bag|basket", re.I)
    if _click_first(page, page.get_by_role("link", name=rx)) or _click_first(
            page, page.get_by_role("button", name=rx)):
        return True
    for route in ("/cart", "/warenkorb", "/bag", "/basket"):
        try:
            page.goto(base + route, timeout=8000)
            page.wait_for_timeout(400)
            return True
        except Exception:
            continue
    return False


def _cart_line_item(page) -> bool:
    """A REAL cart line item is present — a row carrying a price plus a qty/remove control (not just any
    price text). Distinguishes a populated cart from an empty one that merely shows a price somewhere."""
    for sel in ('[class*="line-item" i]', '[class*="cart-item" i]', '[data-testid*="cart" i] li',
                '[class*="cart" i] li', "table tbody tr"):
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    # fallback: a qty control co-located with a price strongly implies a populated cart row
    try:
        qty = page.locator('input[type="number"], [class*="qty" i], [aria-label*="quantity" i]').count()
        return qty > 0 and _has_price(page)
    except Exception:
        return False


def _seed_cart(page, base: str) -> None:
    """Put a real item in the cart, sharing the browser's session. Try the UI first (PDP → add), then
    fall back to the discovered REST cart endpoints via page.request (same cookie jar, so a per-session
    server cart is actually populated). Best-effort — never raises."""
    if _count_cards(page) < 1:
        _open_listing(page, base)
    _open_pdp(page)
    _add_to_cart(page)
    try:
        page.wait_for_timeout(500)
    except Exception:
        pass
    if _open_cart(page, base) and _cart_line_item(page):
        return
    # UI add didn't populate a visible cart — seed via the cart API on the SAME session, then re-open
    for path in _CART_PATHS:
        for payload in ({"productId": "1", "quantity": 1}, {"sku": "1", "qty": 1, "size": "M"},
                        {"id": "1", "quantity": 1, "size": "M"}):
            try:
                resp = page.request.post(base + path, data=json.dumps(payload),
                                         headers={"content-type": "application/json"}, timeout=6000)
                if resp.ok:
                    _open_cart(page, base)
                    if _cart_line_item(page):
                        return
            except Exception:
                continue


def _on_checkout(page, base: str) -> bool:
    """The checkout surface was actually REACHED — a checkout route or a payment/address form is present
    (structural), not merely a 'Checkout' link/text sitting in a footer."""
    try:
        if re.search(r"/(checkout|kasse|payment|pay|bestellung)", page.url, re.I):
            return True
    except Exception:
        pass
    for sel in ('form input[autocomplete]', 'input[name*="card" i]', 'input[name*="email" i]',
                '[id*="stripe" i]', '[class*="checkout" i] form', 'form [name*="address" i]'):
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False


def _eval_journey(page, base: str, journey: dict, egress: bool) -> tuple[bool, bool]:
    """Navigate to the journey's screen, then require its evaluable checks to hold. Returns
    (passed, evaluable): a journey with NO evaluable check (e.g. a stateful flow the sandbox cannot
    drive) is reported evaluable=False so the scorer excludes it instead of counting a hard fail."""

    jid = journey.get("id")
    if jid == "home":
        try:
            page.goto(base, timeout=12000)
            page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            return False, True  # home is always evaluable; a navigation failure is a real fail
    elif jid == "browse_filter":
        _open_listing(page, base)
    elif jid == "pdp":
        if _count_cards(page) < 1:
            _open_listing(page, base)
        _open_pdp(page)
    elif jid == "cart":
        _seed_cart(page, base)  # drive a real item into the cart (UI, then session-shared REST)
    elif jid == "checkout_payment":
        if _count_cards(page) < 1 or not _cart_line_item(page):
            _seed_cart(page, base)  # must have a cart to reach checkout (a correct app redirects if empty)
        _click_first(page, page.get_by_role("link", name=re.compile(r"checkout|kasse|pay", re.I))) or \
            _click_first(page, page.get_by_role("button", name=re.compile(r"checkout|kasse|pay", re.I)))

    passed, evaluable = True, 0
    for check in journey.get("checks", []):
        try:
            ok, counts = _eval_check(page, check, egress, base)
        except Exception:
            ok, counts = False, True
        if counts:
            evaluable += 1
            passed = passed and ok
    return (passed and evaluable > 0), evaluable > 0


def _eval_check(page, check: dict, egress: bool, base: str = "") -> tuple[bool, bool]:
    """(passed, is_evaluable). A check that the sandbox cannot drive (a stateful cart/checkout that could
    not be seeded, payment without egress) is reported NOT evaluable so the scorer excludes it — rather
    than crediting incidental keyword text or hard-failing a flow no arm can complete."""

    if "role_any" in check:
        return any(_role(page, r) for r in check["role_any"]), True
    if "role" in check:
        if check["role"] == "searchbox":  # "a search input is present", however it's implemented
            return _has_search(page), True
        return _role(page, check["role"]), True
    if "name_re" in check:
        return _named(page, check["name_re"]), True
    if "min_cards" in check:
        return _count_cards(page) >= check["min_cards"], True
    if "min_line_items" in check:
        return _cart_line_item(page), True
    if "requires" in check:
        need = set(check["requires"])
        have = {
            "image": page.locator("img").evaluate_all(
                "(images) => images.some(img => img.complete && img.naturalWidth > 0)"
            ),
            "price": _has_price(page), "variant_select": _has_variant(page),
        }
        return all(have.get(r, False) for r in need), True
    if check.get("interaction") == "filter_or_sort":
        try:
            ok = page.locator("select").count() > 0 or page.get_by_role(
                "button", name=re.compile(r"filter|sort|sortieren", re.I)).count() > 0
        except Exception:
            ok = False
        return ok, True
    if check.get("interaction") == "update_qty_remove":
        try:
            ok = page.locator('input[type="number"], [class*="qty" i], [aria-label*="quantity" i]').count() > 0
        except Exception:
            ok = False
        return ok, True
    if check.get("interaction") == "checkout":
        return _on_checkout(page, base), True
    if check.get("kind") == "payment" or check.get("mode") == "stripe_test":
        return False, False  # no payment driver exists; never report a candidate payment failure
    if check.get("kind") == "state":
        return _arith_consistent(page), True
    return False, False


def _arith_consistent(page) -> bool:
    """Best-effort: subtotal + delivery - discount == total, parsed from the cart page text."""
    try:
        text = page.inner_text("body")
    except Exception:
        return False

    def _amount(label: str) -> int | None:
        # non-capturing group around the label alternation, else `a|b(num)` makes group(1) None
        m = re.search(rf"(?:{label})[^0-9\-]{{0,20}}(-?\d+[.,]\d{{2}})", text, re.I)
        return round(float(m.group(1).replace(",", ".")) * 100) if m else None

    sub, total = _amount("subtotal|zwischensumme"), _amount("total|gesamt|summe")
    if sub is None or total is None:
        return False
    delivery = _amount("delivery|shipping|versand") or 0
    discount = _amount("discount|rabatt") or 0
    return abs(total - (sub + delivery - discount)) <= 1


def _check_pwa_a11y(page, base: str, acceptance: dict) -> list[dict]:
    """Offline PWA + a11y checks over the rendered home page (no network / axe CDN needed)."""

    out: list[dict] = []
    ids = {c["id"] for c in acceptance.get("pwa", [])} | {c["id"] for c in acceptance.get("a11y", [])}

    def add(cid: str, ok: bool, detail: str = "") -> None:
        if cid in ids:
            out.append({"id": cid, "passed": bool(ok), "detail": detail})

    # PWA: manifest linked + valid, service worker registered, installable (both), responsive
    manifest_href = None
    try:
        manifest_href = page.evaluate(
            "() => { const l = document.querySelector('link[rel=manifest]'); return l && l.href; }")
    except Exception:
        pass
    manifest_ok = False
    if manifest_href:
        path = manifest_href.split(base, 1)[-1] if base in manifest_href else "/manifest.webmanifest"
        status, body = _get(base, path)
        try:
            data = json.loads(body) if status == 200 else {}
            manifest_ok = all(k in data for k in ("name", "icons", "start_url", "display"))
        except (json.JSONDecodeError, ValueError):
            manifest_ok = False
    add("manifest", manifest_ok, f"href={manifest_href}")

    sw_ok = False
    try:
        page.wait_for_timeout(800)
        sw_ok = bool(page.evaluate(
            "async () => { if (!('serviceWorker' in navigator)) return false;"
            " const r = await navigator.serviceWorker.getRegistrations(); return r.length > 0; }"))
    except Exception:
        sw_ok = False
    add("service_worker", sw_ok)
    add("installable", manifest_ok and sw_ok)

    responsive_ok = True
    try:
        for w in (390, 1280):
            page.set_viewport_size({"width": w, "height": 900})
            page.wait_for_timeout(250)
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - window.innerWidth")
            responsive_ok = responsive_ok and overflow <= 4
        page.set_viewport_size({"width": 1280, "height": 900})
    except Exception:
        responsive_ok = False
    add("responsive", responsive_ok)

    # a11y: landmarks, image alt-text, accessible names, an offline "critical violation" heuristic
    add("landmarks", _role(page, "banner") and _role(page, "main") and (
        _role(page, "navigation") or _role(page, "contentinfo")))
    try:
        alt = page.evaluate(
            "() => { const i = [...document.images]; if (!i.length) return 1;"
            " return i.filter(x => x.alt && x.alt.trim()).length / i.length; }")
    except Exception:
        alt = 0
    add("alt_text", alt >= 0.8, f"alt_ratio={alt:.2f}")
    try:
        unnamed = page.evaluate(
            "() => [...document.querySelectorAll('button,a')].filter(e =>"
            " !(e.innerText||'').trim() && !e.getAttribute('aria-label')"
            " && !e.getAttribute('title')).length")
    except Exception:
        unnamed = 1
    add("keyboard", unnamed == 0, f"unnamed_controls={unnamed}")
    try:
        crit = page.evaluate(
            "() => { let n = 0;"
            " if (!document.documentElement.lang) n++;"
            " n += [...document.images].filter(x => !x.alt).length ? 1 : 0;"
            " const ids = [...document.querySelectorAll('[id]')].map(e=>e.id);"
            " if (new Set(ids).size !== ids.length) n++; return n; }")
    except Exception:
        crit = 1
    add("axe", crit == 0, f"critical_heuristic={crit}")
    return out


def run_ui(base: str, acceptance: dict, artifacts: str) -> dict:
    """Playwright per-journey navigation + assertions, screenshots, and PWA/a11y. Guarded if absent."""

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {"available": False}
    egress = os.environ.get("GAUNTLET_EGRESS") == "1"
    out: dict = {"available": True, "journeys": [], "screenshots": {}, "pwa_a11y": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(base, timeout=15000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            out["pwa_a11y"] = _check_pwa_a11y(page, base, acceptance)  # before journeys mutate nav state
            for journey in acceptance.get("journeys", []):
                jpassed, jeval = _eval_journey(page, base, journey, egress)
                out["journeys"].append(
                    {"id": journey["id"], "passed": jpassed, "evaluable": jeval})
                screen = {"browse_filter": "listing"}.get(journey["id"], journey["id"])
                if jpassed and any(a["screen"] == screen for a in acceptance.get("visual_anchors", [])):
                    shot = os.path.join(artifacts, f"{screen}.png")
                    page.screenshot(path=shot, full_page=True)
                    out["screenshots"][screen] = shot
                    out.setdefault("screenshot_urls", {})[screen] = page.url
        finally:
            browser.close()
    return out


def main(argv: list[str]) -> int:
    workdir, acceptance_path, artifacts = argv[1], argv[2], argv[3]
    acceptance = json.loads(open(acceptance_path).read())  # noqa: SIM115
    serve = json.loads(os.environ.get("GAUNTLET_SERVE", "[]"))
    port = int(os.environ.get("GAUNTLET_PORT", "8080"))
    ready_path = os.environ.get("GAUNTLET_READY", acceptance.get("start", {}).get("ready_path", "/"))
    base = f"http://127.0.0.1:{port}"
    os.makedirs(artifacts, exist_ok=True)

    proc = None
    served = False
    if serve:
        env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1"}
        proc = subprocess.Popen(serve, cwd=workdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        served = wait_ready(base, ready_path)
    def _safe(fn, default):  # never let a probe section crash the run — a result.json must always land
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            return default if not isinstance(default, dict) else {**default, "error": str(exc)[:200]}

    try:
        ui = _safe(lambda: run_ui(base, acceptance, artifacts), {"available": False}) if served \
            else {"available": False}
        result = {
            "served": served,
            "rest": _safe(lambda: check_rest(base, acceptance.get("rest_contracts", [])), []) if served else [],
            "robustness": _safe(lambda: check_robustness(base, acceptance.get("robustness", [])), []) if served else [],
            "ui": ui,
            "pwa_a11y": ui.get("pwa_a11y", []),
        }
    finally:
        if proc is not None:
            proc.terminate()
    with open(os.path.join(artifacts, "result.json"), "w") as fh:
        json.dump(result, fh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
