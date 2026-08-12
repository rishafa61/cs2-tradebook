"""
Reference-price math for CS2 skin sales.

The problem: marketplaces take a cut (CSFloat 2%, Buff163 ~2.5%, Steam
~13%, Skinport ~12%, etc). If you list an item at exactly what you want
back, the fee eats into it and you net less than you meant to. This
module works backwards: given what you want to walk away with (your
cost basis + a minimum profit), it tells you the lowest listing price
that guarantees that after the fee is taken out.
"""

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

CENT = Decimal("0.01")


def min_sell_price(cost_basis, fee_rate, min_profit=Decimal("0")):
    """
    cost_basis: what you already have into the item (or any net amount
                you want to be guaranteed to receive), as a Decimal/str/float.
    fee_rate:   marketplace fee as a fraction, e.g. Decimal("0.02") for 2%.
    min_profit: minimum profit you want to clear on top of cost_basis.

    Returns a dict with the lowest listing price (rounded UP to the
    nearest cent, so the guarantee always holds after rounding), the
    fee taken at that price, the net proceeds, and the actual profit.
    """
    cost_basis = Decimal(str(cost_basis))
    fee_rate = Decimal(str(fee_rate))
    min_profit = Decimal(str(min_profit))

    if fee_rate < 0 or fee_rate >= 1:
        raise ValueError("Fee rate must be between 0% and 100%.")
    if cost_basis < 0 or min_profit < 0:
        raise ValueError("Cost basis and minimum profit must be positive.")

    target_net = cost_basis + min_profit

    if target_net == 0:
        price = Decimal("0.00")
    else:
        raw_price = target_net / (Decimal("1") - fee_rate)
        price = raw_price.quantize(CENT, rounding=ROUND_CEILING)

    def _at(price):
        fee_amount = (price * fee_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        net_proceeds = price - fee_amount
        return fee_amount, net_proceeds

    fee_amount, net_proceeds = _at(price)

    # Marketplaces round their fee too, which can occasionally shave a
    # cent off net proceeds even after our ceiling above. Nudge the
    # price up cent-by-cent until the guarantee actually holds.
    while net_proceeds < target_net:
        price += CENT
        fee_amount, net_proceeds = _at(price)

    return {
        "list_price": price,
        "fee_amount": fee_amount,
        "net_proceeds": net_proceeds,
        "actual_profit": (net_proceeds - cost_basis).quantize(CENT, rounding=ROUND_HALF_UP),
        "target_net": target_net.quantize(CENT, rounding=ROUND_HALF_UP),
    }
