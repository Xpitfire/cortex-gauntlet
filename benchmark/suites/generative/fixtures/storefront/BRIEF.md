# Build brief — fashion e-commerce storefront ("Atelier")

You are building a complete, runnable web application **repository** from scratch. This is an
open-ended task: **you decide the architecture, stack, structure, and file layout.** What matters is
that the product works, looks the part, and is engineered like real production software.

## What the product is

A modern online **fashion storefront** — think a large multi-brand clothing & shoes retailer
(à la Zalando). A shopper can discover products, drill into a product, choose a size/variant, add it
to a cart, and complete a checkout with a (test-mode) payment. The reference screenshots in
`screenshots/` show the target look and the core screens — match that visual quality and UX, but the
implementation is entirely yours.

Reference frames (in `screenshots/`):
- `01-home.png` — landing page: top sale banner, brand header (logo, Damen/Herren/Kinder, search,
  account/wishlist/cart icons), category nav bar, a hero carousel, and a brand grid.
- `02-mega-nav.png` — category mega-menu (Damen/Herren/Kinder columns with sub-categories) over a
  product listing.
- `03-listing.png` — category/product listing page: breadcrumb, title, filter pills
  (sort/brand/size/color/price/…), result count, and a responsive product grid (image, brand, name,
  price, wishlist heart).
- `04-pdp.png` — product detail page: image gallery/thumbnails, brand + title, price, color swatches,
  size selector, "add to cart", delivery info, seller info.
- `05-cart.png` — cart page: line items (image, name, price, color/size, qty), order summary
  (subtotal, delivery, total), accepted-payment badges, and a "checkout" action.

## What it must do (outcomes, not a blueprint)

A shopper can:
1. Land on a home page with category navigation and featured content.
2. Browse a category and use at least one working **filter/sort** over a product grid.
3. Open a **product detail page**, see images + price, and select a **size/variant**.
4. **Add to cart**, then view the cart and **update quantity / remove** items, with correct
   **subtotal, delivery, and total** math (integer-cents, tax/shipping rules your choice but stated).
5. Proceed through a **checkout** flow and complete a **payment using Stripe test mode** (demo keys,
   test cards — never a real charge), landing on an **order confirmation**.

Engineering expectations (deliver as outcomes; choose how):
- A real **backend** (catalog, cart, checkout/orders) with a documented HTTP API.
- A **frontend** that is a **Progressive Web App**: installable (web app manifest), a **service
  worker** with an offline shell, responsive layout for mobile + desktop.
- Reasonable **accessibility**: semantic landmarks, image alt text, keyboard-navigable controls.
- **Automated tests** for the core flows, and a build/CI manifest.
- Clean, modular, typed code with sensible separation of concerns.

## Constraints & givens

- **Self-contained & runnable**: provide one documented command (e.g. a `Makefile`/`package.json`
  script/README) that installs, builds, and serves the app, binding to `127.0.0.1:$PORT`. It must run
  with no external network beyond the package registry (install) and the Stripe **test** endpoint.
- **Payments**: Stripe **test mode** only — use Stripe's published test publishable key pattern and
  test cards; the flow must reach a confirmed test payment without real money.
- **Auth** may be a lightweight stub (guest checkout is fine).
- **Seed data**: a small product catalog is provided in `catalog.json` (brands, products, variants,
  prices, images) — use it; you may extend it.
- Keep secrets out of the repo; read any keys from the environment.

## How you'll be judged (so you know what to optimize)

Your repository is built and run in an isolated sandbox, then scored on: whether it builds & boots;
how many of the shopper journeys above actually work end-to-end (real browser + API tests); PWA &
accessibility checks; visual fidelity of the rendered screens vs. the reference frames; code quality
& architecture; and robustness to bad input. Partial, well-structured progress is credited — but a
broken build is not. Build it like you would ship it.
