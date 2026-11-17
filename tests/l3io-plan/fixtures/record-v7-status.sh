#!/usr/bin/env bash
# Re-record v7-status-shop.json and v7-status-portfolio.json with BMad v7's own tickets.py.
#
# Usage: tests/l3io-plan/fixtures/record-v7-status.sh <path to tickets.py at the pin>
#
# The JSON is what `tickets.py status` prints for a hand-written tree: a parent initiative
# (portfolio) over four initiatives, and one of them (shop) with five epics whose `after`
# graph exercises every edge plan-graph.py's `waves` reads -- a declared `[[epic]] after`, an
# entry `after` into another epic that the epic does not declare, and an epic file's own
# `after`, the one kind that waits for the prerequisite epic to be `done`.
set -euo pipefail

tickets_py="${1:?usage: $0 <tickets.py>}"
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/_bmad"
out="$work/_bmad-output"

w() { mkdir -p "$(dirname "$1")"; cat >"$1"; }

w "$out/portfolio/portfolio.md" <<'EOF'
---
type: initiative
---
# Portfolio
EOF
w "$out/portfolio/tickets/tickets.toml" <<'EOF'
[[initiative]]
id = 1
slug = "shop"
title = "Shop"

[[initiative]]
id = 2
slug = "ops"
title = "Operations"
after = [{ initiative = 1, needs = "the shop's order events to monitor" }]

[[initiative]]
id = 3
slug = "growth"
title = "Growth"
after = [{ initiative = 1, needs = "a live storefront to grow" }]

[[initiative]]
id = 4
slug = "insights"
title = "Insights"
after = [{ initiative = 2, needs = "the operations metrics feed" }, { initiative = 3, needs = "campaign results to report on" }]
EOF
w "$out/shop/shop.md" <<'EOF'
---
type: initiative
status: in-progress
---
# Shop
EOF
w "$out/shop/tickets/tickets.toml" <<'EOF'
[[epic]]
id = 1
slug = "epic-platform"
title = "Platform"

[[epic]]
id = 2
slug = "epic-cart"
title = "Cart"
after = [{ epic = 1, needs = "sessions and the product catalogue" }]

[[epic]]
id = 3
slug = "epic-search"
title = "Search"
after = [{ epic = 1, needs = "the catalogue index" }]

[[epic]]
id = 4
slug = "epic-checkout"
title = "Checkout"
after = [{ epic = 2, needs = "a basket to pay for" }]

[[epic]]
id = 5
slug = "epic-docs"
title = "Docs"
EOF
e="$out/shop/tickets"
w "$e/epic-platform/epic-platform.md" <<'EOF'
---
type: epic
status: in-progress
after: []
---
# Platform
EOF
w "$e/epic-platform/tickets/tickets.toml" <<'EOF'
[[entry]]
id = 1
type = "story"
title = "Sessions"
description = "Sign-in sessions."
verify = "a session survives a reload"

[[entry]]
id = 2
type = "story"
title = "Catalogue index"
description = "Index the catalogue."
verify = "a product is found by name"
after = [1]
EOF
w "$e/epic-platform/tickets/story-sessions-plan.md" <<'EOF'
---
title: 'Sessions'
type: 'feature'
ticket: '1'
status: 'built'
review_loop_iteration: 1
---

# Sessions
EOF
w "$e/epic-cart/epic-cart.md" <<'EOF'
---
type: epic
after: []
---
# Cart
EOF
w "$e/epic-cart/tickets/tickets.toml" <<'EOF'
[[entry]]
id = 1
type = "story"
title = "Basket"
description = "A basket that survives a reload."
verify = "reload keeps the basket"
after = ["1.1"]
EOF
w "$e/epic-cart/tickets/story-basket-plan.md" <<'EOF'
---
title: 'Basket'
type: 'feature'
ticket: '1'
status: 'in-progress'
---

# Basket
EOF
w "$e/epic-search/epic-search.md" <<'EOF'
---
type: epic
after: []
---
# Search
EOF
w "$e/epic-search/tickets/tickets.toml" <<'EOF'
[[entry]]
id = 1
type = "story"
title = "Search box"
description = "Search the catalogue, adding to the basket from results."
verify = "a search result goes into the basket"
after = ["1.2", "2.1"]
EOF
w "$e/epic-checkout/epic-checkout.md" <<'EOF'
---
type: epic
after: [epic-cart]
---
# Checkout
EOF
w "$e/epic-checkout/tickets/tickets.toml" <<'EOF'
[[entry]]
id = 1
type = "story"
title = "Pay"
description = "Pay for the basket."
verify = "a paid order is recorded"
EOF
w "$e/epic-docs/epic-docs.md" <<'EOF'
---
type: epic
after: []
---
# Docs
EOF
w "$e/epic-docs/tickets/tickets.toml" <<'EOF'
[[entry]]
id = 1
type = "story"
title = "Guide"
description = "A shopper's guide."
verify = "the guide renders"
EOF

cd "$work"
uv run --quiet "$tickets_py" --project-root . status "$out/shop" >"$here/v7-status-shop.json"
uv run --quiet "$tickets_py" --project-root . status "$out/portfolio" >"$here/v7-status-portfolio.json"
