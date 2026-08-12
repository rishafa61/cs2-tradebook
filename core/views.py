from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    P2PGivenItemFormSet,
    P2PReceivedItemFormSet,
    P2PTradeForm,
    TransactionForm,
)
from .models import (
    MARKETPLACE_CHOICES,
    InventoryItem,
    P2PGivenItem,
    P2PReceivedItem,
    P2PTrade,
    Transaction,
    two_places,
)
from .pricing import min_sell_price

# Typical marketplace cuts, used to prefill the fee % when a marketplace
# is picked on the sell calculator. Users can always override the number.
MARKETPLACE_FEE_DEFAULTS = {
    "csfloat": Decimal("2"),
    "buff163": Decimal("2.5"),
    "steam": Decimal("13"),
    "skinport": Decimal("12"),
    "other": Decimal("2"),
}


# ---------------------------------------------------------------------------
# Transaction inventory sync helpers
# ---------------------------------------------------------------------------

def _revert_buy(inventory_item):
    if inventory_item and inventory_item.status == "holding":
        inventory_item.delete()


def _revert_sell(inventory_item):
    if inventory_item:
        inventory_item.status = "holding"
        inventory_item.save()


def _apply_buy(txn):
    if txn.inventory_item_id:
        inv = txn.inventory_item
        inv.skin_name = txn.skin_name
        inv.purchase_price = txn.buy_price
        inv.purchase_date = txn.date
        inv.save()
    else:
        inv = InventoryItem.objects.create(
            skin_name=txn.skin_name,
            purchase_price=txn.buy_price,
            estimated_price=txn.buy_price,
            purchase_date=txn.date,
            status="holding",
        )
        txn.inventory_item = inv


def _apply_sell(txn, inventory_item):
    txn.skin_name = inventory_item.skin_name
    txn.buy_price = inventory_item.purchase_price
    inventory_item.status = "sold"
    inventory_item.save()
    txn.inventory_item = inventory_item


def _save_transaction(form, instance_original=None):
    txn = form.save(commit=False)
    old_type = instance_original.type if instance_original else None
    old_inventory = instance_original.inventory_item if instance_original else None

    if old_type == "buy" and txn.type == "buy":
        txn.inventory_item = old_inventory
        _apply_buy(txn)
    elif old_type == "sell" and txn.type == "sell":
        new_inventory = form.cleaned_data.get("inventory_item")
        if old_inventory and new_inventory and old_inventory.pk == new_inventory.pk:
            _apply_sell(txn, new_inventory)
        else:
            _revert_sell(old_inventory)
            _apply_sell(txn, new_inventory)
    else:
        if old_type == "buy":
            _revert_buy(old_inventory)
        elif old_type == "sell":
            _revert_sell(old_inventory)
        txn.inventory_item = None
        if txn.type == "buy":
            _apply_buy(txn)
        elif txn.type == "sell":
            _apply_sell(txn, form.cleaned_data.get("inventory_item"))
        else:
            txn.inventory_item = None
            txn.skin_name = ""

    txn.save()
    return txn


# ---------------------------------------------------------------------------
# P2P helpers
# ---------------------------------------------------------------------------

def _apply_p2p(trade, given_rows, received_rows):
    """
    Mark every given skin as traded, and create a new inventory item for
    every received skin.

    given_rows: list of dicts like {"inventory_item": InventoryItem, "value": Decimal}
    received_rows: list of dicts like {"skin_name": str, "value": Decimal}

    The combined cost basis (total given value + any cash you added) is
    split across the received items in proportion to their agreed value,
    so per-item unrealized P&L stays meaningful even for multi-item trades.
    """
    total_given_value = sum((row["value"] for row in given_rows), Decimal("0"))
    total_received_value = sum((row["value"] for row in received_rows), Decimal("0"))
    total_cost_basis = total_given_value + trade.effective_cash_paid

    for row in given_rows:
        item = row["inventory_item"]
        item.status = "traded"
        item.save()
        P2PGivenItem.objects.create(
            trade=trade, inventory_item=item, skin_name=item.skin_name, value=row["value"],
        )

    n_received = len(received_rows)
    for i, row in enumerate(received_rows):
        if total_received_value:
            share = row["value"] / total_received_value
        else:
            share = Decimal("1") / n_received
        item_cost_basis = two_places(total_cost_basis * share)

        received_item = InventoryItem.objects.create(
            skin_name=row["skin_name"],
            purchase_price=item_cost_basis,
            estimated_price=row["value"],
            purchase_date=trade.date,
            status="holding",
        )
        P2PReceivedItem.objects.create(
            trade=trade, skin_name=row["skin_name"], value=row["value"], inventory_item=received_item,
        )


def _revert_p2p(trade):
    """Undo a P2P: restore every given skin to holding, remove every received skin."""
    for line in trade.given_lines.all():
        if line.inventory_item:
            line.inventory_item.status = "holding"
            line.inventory_item.save()
    for line in trade.received_lines.all():
        if line.inventory_item:
            line.inventory_item.delete()
    trade.given_lines.all().delete()
    trade.received_lines.all().delete()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard(request):
    buys = Transaction.objects.filter(type="buy")
    sells = Transaction.objects.filter(type="sell")
    deposits = Transaction.objects.filter(type="deposit")
    withdrawals = Transaction.objects.filter(type="withdraw")
    p2p_trades = P2PTrade.objects.all()

    total_invested = sum((t.buy_price or 0) for t in buys)
    total_fees = sum((t.marketplace_fee or 0) + (t.other_fee or 0) for t in sells)
    realized_profit = sum((t.net_profit or 0) for t in sells)

    total_deposits = sum((t.amount or 0) for t in deposits)
    total_withdrawals = sum((t.amount or 0) for t in withdrawals)
    net_sale_cash = sum(
        (t.sell_price or 0) - (t.marketplace_fee or 0) - (t.other_fee or 0) for t in sells
    )

    # P2P cash impact: cash received adds to balance, cash paid reduces it
    p2p_cash_in = sum(t.effective_cash_received for t in p2p_trades)
    p2p_cash_out = sum(t.effective_cash_paid for t in p2p_trades)

    cash_available = two_places(
        Decimal(total_deposits)
        + Decimal(net_sale_cash)
        - Decimal(total_invested)
        - Decimal(total_withdrawals)
        + Decimal(p2p_cash_in)
        - Decimal(p2p_cash_out)
    )

    holding_items = InventoryItem.objects.filter(status="holding")
    inventory_value = sum((i.estimated_price or 0) for i in holding_items)
    unrealized_profit = sum((i.unrealized_profit or 0) for i in holding_items)

    p2p_realized = sum((t.net_gain or 0) for t in p2p_trades)
    total_trades = buys.count() + sells.count() + p2p_trades.count()

    context = {
        "cash_available": cash_available,
        "total_invested": two_places(total_invested),
        "inventory_value": two_places(inventory_value),
        "realized_profit": two_places(realized_profit + p2p_realized),
        "unrealized_profit": two_places(unrealized_profit),
        "total_fees": two_places(total_fees),
        "total_trades": total_trades,
        "recent_transactions": Transaction.objects.all()[:5],
        "recent_p2p": P2PTrade.objects.all()[:3],
        "inventory_items": holding_items[:8],
    }
    return render(request, "core/dashboard.html", context)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def transaction_list(request):
    qs = Transaction.objects.all()
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(Q(skin_name__icontains=search) | Q(notes__icontains=search))
    month = request.GET.get("month", "").strip()
    if month:
        try:
            year, mon = month.split("-")
            qs = qs.filter(date__year=int(year), date__month=int(mon))
        except (ValueError, IndexError):
            pass
    sort = request.GET.get("sort", "-date")
    if sort not in ("date", "-date"):
        sort = "-date"
    qs = qs.order_by(sort, "-id")
    return render(request, "core/transaction_list.html", {
        "transactions": qs, "search": search, "month": month, "sort": sort,
    })


def transaction_add(request):
    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            _save_transaction(form)
            messages.success(request, "Transaction added.")
            return redirect("transaction-list")
    else:
        form = TransactionForm(initial={"date": date.today().isoformat()})
    return render(request, "core/transaction_form.html", {"form": form, "mode": "add"})


def transaction_edit(request, pk):
    original = get_object_or_404(Transaction, pk=pk)
    if request.method == "POST":
        form = TransactionForm(request.POST, instance=Transaction.objects.get(pk=pk))
        if form.is_valid():
            _save_transaction(form, instance_original=original)
            messages.success(request, "Transaction updated.")
            return redirect("transaction-list")
    else:
        initial = {}
        if original.type == "sell" and original.inventory_item_id:
            initial["inventory_item"] = original.inventory_item_id
        form = TransactionForm(instance=original, initial=initial)
    return render(request, "core/transaction_form.html", {"form": form, "mode": "edit", "txn": original})


def transaction_delete(request, pk):
    txn = get_object_or_404(Transaction, pk=pk)
    if request.method == "POST":
        if txn.type == "buy":
            _revert_buy(txn.inventory_item)
        elif txn.type == "sell":
            _revert_sell(txn.inventory_item)
        txn.delete()
        messages.success(request, "Transaction deleted.")
        return redirect("transaction-list")
    return render(request, "core/transaction_confirm_delete.html", {"txn": txn})


# ---------------------------------------------------------------------------
# P2P Trades
# ---------------------------------------------------------------------------

def p2p_list(request):
    trades = P2PTrade.objects.all()
    search = request.GET.get("q", "").strip()
    if search:
        trades = trades.filter(
            Q(given_lines__skin_name__icontains=search) |
            Q(received_lines__skin_name__icontains=search) |
            Q(notes__icontains=search)
        ).distinct()
    month = request.GET.get("month", "").strip()
    if month:
        try:
            year, mon = month.split("-")
            trades = trades.filter(date__year=int(year), date__month=int(mon))
        except (ValueError, IndexError):
            pass
    return render(request, "core/p2p_list.html", {"trades": trades, "search": search, "month": month})


def _p2p_rows_from_formset(formset, item_field, value_field="value"):
    """Extract non-deleted, non-blank cleaned rows from a validated formset."""
    rows = []
    for f in formset.forms:
        if not hasattr(f, "cleaned_data") or not f.cleaned_data:
            continue
        if f.cleaned_data.get("DELETE"):
            continue
        item = f.cleaned_data.get(item_field)
        value = f.cleaned_data.get(value_field)
        if item and value is not None:
            rows.append({item_field: item, value_field: value})
    return rows


def p2p_add(request):
    holding_qs = InventoryItem.objects.filter(status="holding")
    if request.method == "POST":
        form = P2PTradeForm(request.POST)
        given_formset = P2PGivenItemFormSet(
            request.POST, prefix="given", form_kwargs={"inventory_qs": holding_qs},
        )
        received_formset = P2PReceivedItemFormSet(request.POST, prefix="received")
        if form.is_valid() and given_formset.is_valid() and received_formset.is_valid():
            given_rows = _p2p_rows_from_formset(given_formset, "inventory_item")
            received_rows = _p2p_rows_from_formset(received_formset, "skin_name")

            trade = form.save(commit=False)
            trade.save()
            _apply_p2p(trade, given_rows, received_rows)
            messages.success(
                request,
                f"P2P trade recorded: {trade.given_skin_names} → {trade.received_skin_names}. "
                f"{trade.received_skin_names} added to inventory."
            )
            return redirect("p2p-list")
    else:
        form = P2PTradeForm(initial={"date": date.today().isoformat()})
        given_formset = P2PGivenItemFormSet(prefix="given", form_kwargs={"inventory_qs": holding_qs})
        received_formset = P2PReceivedItemFormSet(prefix="received")
    return render(request, "core/p2p_form.html", {
        "form": form,
        "given_formset": given_formset,
        "received_formset": received_formset,
        "mode": "add",
    })


def p2p_edit(request, pk):
    trade = get_object_or_404(P2PTrade, pk=pk)
    # Allow re-selecting the skins already part of this trade (they're
    # currently marked "traded", not "holding") alongside anything else
    # that's currently free.
    holding_qs = InventoryItem.objects.filter(
        Q(status="holding") | Q(p2p_given_lines__trade=trade)
    ).distinct()

    if request.method == "POST":
        form = P2PTradeForm(request.POST, instance=trade)
        given_formset = P2PGivenItemFormSet(
            request.POST, prefix="given", form_kwargs={"inventory_qs": holding_qs},
        )
        received_formset = P2PReceivedItemFormSet(request.POST, prefix="received")
        if form.is_valid() and given_formset.is_valid() and received_formset.is_valid():
            given_rows = _p2p_rows_from_formset(given_formset, "inventory_item")
            received_rows = _p2p_rows_from_formset(received_formset, "skin_name")

            _revert_p2p(trade)
            updated = form.save(commit=False)
            updated.save()
            _apply_p2p(updated, given_rows, received_rows)
            messages.success(request, "P2P trade updated.")
            return redirect("p2p-list")
    else:
        form = P2PTradeForm(instance=trade)
        given_initial = [
            {"inventory_item": line.inventory_item_id, "value": line.value}
            for line in trade.given_lines.all()
        ]
        received_initial = [
            {"skin_name": line.skin_name, "value": line.value}
            for line in trade.received_lines.all()
        ]
        given_formset = P2PGivenItemFormSet(
            initial=given_initial, prefix="given", form_kwargs={"inventory_qs": holding_qs},
        )
        received_formset = P2PReceivedItemFormSet(initial=received_initial, prefix="received")
    return render(request, "core/p2p_form.html", {
        "form": form,
        "given_formset": given_formset,
        "received_formset": received_formset,
        "mode": "edit",
        "trade": trade,
    })


def p2p_delete(request, pk):
    trade = get_object_or_404(P2PTrade, pk=pk)
    if request.method == "POST":
        _revert_p2p(trade)
        trade.delete()
        messages.success(request, "P2P trade deleted. Skin restored to inventory.")
        return redirect("p2p-list")
    return render(request, "core/p2p_confirm_delete.html", {"trade": trade})


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def inventory_list(request):
    items = InventoryItem.objects.filter(status="holding")
    return render(request, "core/inventory_list.html", {"items": items})


def inventory_update_estimate(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, status="holding")
    if request.method == "POST":
        try:
            item.estimated_price = Decimal(request.POST.get("estimated_price"))
            item.save()
            messages.success(request, f"Updated estimated value for {item.skin_name}.")
        except Exception:
            messages.error(request, "Invalid value.")
    return redirect("inventory-list")


# ---------------------------------------------------------------------------
# Sell price calculator
# ---------------------------------------------------------------------------

def sell_calculator(request):
    """
    Reference-price tool: given what you have into an item (or any
    target net amount), a marketplace fee %, and a minimum profit you
    want to clear, work out the lowest listing price that guarantees
    you actually net that much after the fee.
    """
    holding_items = InventoryItem.objects.filter(status="holding")

    marketplace = request.GET.get("marketplace", "csfloat")
    if marketplace not in dict(MARKETPLACE_CHOICES):
        marketplace = "csfloat"

    item_pk = request.GET.get("item", "").strip()
    prefill_item = holding_items.filter(pk=item_pk).first() if item_pk else None

    cost_raw = request.GET.get("cost", "").strip()
    if not cost_raw and prefill_item:
        cost_raw = str(prefill_item.purchase_price)

    fee_raw = request.GET.get("fee_pct", "").strip()
    if not fee_raw:
        fee_raw = str(MARKETPLACE_FEE_DEFAULTS.get(marketplace, Decimal("2")))

    profit_raw = request.GET.get("min_profit", "").strip()
    if not profit_raw:
        profit_raw = "0.01"

    result = None
    error = None

    if cost_raw:
        try:
            cost = Decimal(cost_raw)
            fee_rate = Decimal(fee_raw) / Decimal("100")
            min_profit = Decimal(profit_raw)
            result = min_sell_price(cost, fee_rate, min_profit)
        except (InvalidOperation, ValueError):
            error = "Enter a valid, positive cost, fee %, and minimum profit."

    context = {
        "marketplaces": MARKETPLACE_CHOICES,
        "marketplace": marketplace,
        "cost": cost_raw,
        "fee_pct": fee_raw,
        "min_profit": profit_raw,
        "result": result,
        "error": error,
        "prefill_item": prefill_item,
        "holding_items": holding_items,
        "marketplace_fee_defaults": MARKETPLACE_FEE_DEFAULTS,
    }
    return render(request, "core/sell_calculator.html", context)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def reports(request):
    today = date.today()

    month_buys = Transaction.objects.filter(type="buy", date__year=today.year, date__month=today.month)
    month_sells = Transaction.objects.filter(type="sell", date__year=today.year, date__month=today.month)
    month_p2p = P2PTrade.objects.filter(date__year=today.year, date__month=today.month)

    month_bought = two_places(sum((t.buy_price or 0) for t in month_buys))
    month_sold = two_places(sum((t.sell_price or 0) for t in month_sells))
    month_profit = two_places(
        sum((t.net_profit or 0) for t in month_sells) +
        sum((t.net_gain or 0) for t in month_p2p)
    )
    month_fees = two_places(sum((t.marketplace_fee or 0) + (t.other_fee or 0) for t in month_sells))
    month_p2p_count = month_p2p.count()

    all_buys = Transaction.objects.filter(type="buy")
    all_sells = Transaction.objects.filter(type="sell")
    all_p2p = P2PTrade.objects.all()

    lifetime_investment = two_places(sum((t.buy_price or 0) for t in all_buys))
    lifetime_revenue = two_places(sum((t.sell_price or 0) for t in all_sells))
    sell_profit = sum((t.net_profit or 0) for t in all_sells)
    p2p_profit = sum((t.net_gain or 0) for t in all_p2p)
    lifetime_profit = two_places(sell_profit + p2p_profit)
    lifetime_roi = None
    if lifetime_investment:
        lifetime_roi = two_places((lifetime_profit / lifetime_investment) * 100)

    context = {
        "month_label": today.strftime("%B %Y"),
        "month_bought": month_bought,
        "month_sold": month_sold,
        "month_profit": month_profit,
        "month_fees": month_fees,
        "month_p2p_count": month_p2p_count,
        "lifetime_investment": lifetime_investment,
        "lifetime_revenue": lifetime_revenue,
        "lifetime_profit": lifetime_profit,
        "lifetime_roi": lifetime_roi,
        "total_p2p": all_p2p.count(),
    }
    return render(request, "core/reports.html", context)
