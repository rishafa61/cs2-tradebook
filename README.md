# TradeBook — Personal CS2 Skin Trading Spreadsheet

A Django app for tracking CS2 skin flips: buys, sells, deposits, withdrawals,
inventory, and profit reports. No Steam/CSFloat/Buff163 API calls — everything
is entered manually, but the money math is automatic.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

Open http://127.0.0.1:8000/

## What it does

- **Dashboard** — Cash Available, Total Invested, Inventory Value, Realized
  Profit, Unrealized Profit, Total Fees, Total Trades, plus recent
  transactions and current inventory.
- **Transactions** — spreadsheet-style table of every Buy / Sell / Deposit /
  Withdraw. Add, edit, delete, search, filter by month, sort by date.
- **Inventory** — skins you're currently holding, auto-removed the moment
  you record a Sell against them. You can update each item's Estimated
  Value inline to track unrealized profit.
- **Reports** — This Month and Lifetime summaries (bought, sold, profit,
  fees, ROI).

## CSFloat auto-fee (the feature you asked for)

When you add or edit a **Sell** transaction and set Marketplace to
**CSFloat**, the Marketplace Fee field auto-fills at **2% of the Sell
Price** the moment you type a sell price — so you can see your profit
before you even finish the form. It's a normal field, so you can still
overwrite it by hand (e.g. if CSFloat ever changes its rate, or you want
to model a different fee) — the auto-calc only kicks back in if you clear
the field. This is pure client-side + server-side math, not a live call to
CSFloat — the PRD keeps this app fully offline/manual.

The 2% rate lives in one place if you ever need to change it:
`core/models.py` → `CSFLOAT_FEE_RATE`.

## How Buy/Sell linkage works

- A **Buy** transaction creates an `InventoryItem` (status: Holding).
- A **Sell** transaction asks which held item you're closing out, marks it
  Sold, and computes:
  - `Net Profit = Sell Price - Purchase Price - Marketplace Fee - Other Fee`
  - `ROI = Net Profit / Purchase Price × 100`
- Editing or deleting a Buy/Sell keeps the linked inventory record in sync
  (e.g. deleting a Sell moves the skin back to Holding).

## Tech

Django + SQLite + Django Templates + Bootstrap 5 (CDN), vanilla JS for the
live fee calculation and dark mode toggle. No React/Vue, no external APIs,
single-user (no auth), per the PRD.
