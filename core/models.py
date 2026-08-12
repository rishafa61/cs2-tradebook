from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.urls import reverse

CSFLOAT_FEE_RATE = Decimal("0.02")

MARKETPLACE_CHOICES = [
    ("csfloat", "CSFloat"),
    ("buff163", "Buff163"),
    ("steam", "Steam Community Market"),
    ("skinport", "Skinport"),
    ("other", "Other"),
]

TRANSACTION_TYPE_CHOICES = [
    ("buy", "Buy"),
    ("sell", "Sell"),
    ("deposit", "Deposit"),
    ("withdraw", "Withdraw"),
    ("p2p", "P2P Trade"),
]

STATUS_CHOICES = [
    ("holding", "Holding"),
    ("sold", "Sold"),
    ("traded", "Traded"),
]

CASH_DIRECTION_CHOICES = [
    ("none", "No cash involved (pure swap)"),
    ("received", "I received extra cash"),
    ("paid", "I paid extra cash"),
]


def two_places(value):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class InventoryItem(models.Model):
    skin_name = models.CharField(max_length=200)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2)
    estimated_price = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="holding")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-purchase_date", "-id"]

    def __str__(self):
        return f"{self.skin_name} ({self.get_status_display()})"

    @property
    def unrealized_profit(self):
        if self.status != "holding":
            return Decimal("0.00")
        return two_places(self.estimated_price - self.purchase_price)

    @property
    def holding_days(self):
        from datetime import date
        return (date.today() - self.purchase_date).days


class Transaction(models.Model):
    date = models.DateField()
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    skin_name = models.CharField(max_length=200, blank=True)
    marketplace = models.CharField(max_length=20, choices=MARKETPLACE_CHOICES, blank=True)

    buy_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sell_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    marketplace_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    other_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    notes = models.TextField(blank=True)

    inventory_item = models.ForeignKey(
        InventoryItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sale_transactions",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.skin_name or self.amount} ({self.date})"

    def get_absolute_url(self):
        return reverse("transaction-list")

    @property
    def is_csfloat_sale(self):
        return self.type == "sell" and self.marketplace == "csfloat"

    def auto_marketplace_fee(self):
        if self.is_csfloat_sale and self.sell_price is not None:
            return two_places(Decimal(self.sell_price) * CSFLOAT_FEE_RATE)
        return None

    @property
    def net_profit(self):
        if self.type != "sell":
            return None
        sell = self.sell_price or Decimal("0")
        buy = (self.inventory_item.purchase_price if self.inventory_item else self.buy_price) or Decimal("0")
        fee = self.marketplace_fee or Decimal("0")
        other = self.other_fee or Decimal("0")
        return two_places(sell - buy - fee - other)

    @property
    def roi(self):
        if self.type != "sell":
            return None
        buy = (self.inventory_item.purchase_price if self.inventory_item else self.buy_price) or Decimal("0")
        if not buy:
            return None
        return two_places(((self.net_profit or Decimal("0")) / buy) * 100)

    def save(self, *args, **kwargs):
        if self.is_csfloat_sale and not self.marketplace_fee:
            auto_fee = self.auto_marketplace_fee()
            if auto_fee is not None:
                self.marketplace_fee = auto_fee
        super().save(*args, **kwargs)


class P2PTrade(models.Model):
    """
    A peer-to-peer skin trade. You give one or more skins, you receive one or
    more skins back (many-for-one, one-for-many, or many-for-many all work).
    Optionally one side also pays or receives a cash difference (overpay/underpay).

    Cash effect on balance:
      cash_direction = "received"  →  +cash_amount  (you got sweetener)
      cash_direction = "paid"      →  -cash_amount  (you added cash)
      cash_direction = "none"      →  no cash change (pure swap)

    P&L:
      value_given    = sum of agreed values of the skins you gave up
      value_received = sum of agreed values of the skins you got
      net_gain = (value_received + cash_received) - (value_given + cash_paid)
    """

    date = models.DateField()

    # --- Optional cash difference ---
    cash_direction = models.CharField(
        max_length=10, choices=CASH_DIRECTION_CHOICES, default="none",
    )
    cash_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Cash top-up paid or received on top of the skin swap.",
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"P2P: {self.given_skin_names} → {self.received_skin_names} ({self.date})"

    # ---- Line-item helpers --------------------------------------------

    @property
    def given_skin_names(self):
        names = list(self.given_lines.values_list("skin_name", flat=True))
        return ", ".join(names) if names else "—"

    @property
    def received_skin_names(self):
        names = list(self.received_lines.values_list("skin_name", flat=True))
        return ", ".join(names) if names else "—"

    @property
    def given_value(self):
        """Total agreed value of all skins given away in this trade."""
        total = sum((line.value or Decimal("0") for line in self.given_lines.all()), Decimal("0"))
        return two_places(total)

    @property
    def received_value(self):
        """Total agreed value of all skins received in this trade."""
        total = sum((line.value or Decimal("0") for line in self.received_lines.all()), Decimal("0"))
        return two_places(total)

    # ---- Calculated fields ------------------------------------------------

    @property
    def effective_cash_received(self):
        """Cash that came IN to your balance from this trade."""
        if self.cash_direction == "received":
            return self.cash_amount or Decimal("0")
        return Decimal("0")

    @property
    def effective_cash_paid(self):
        """Cash that went OUT of your balance for this trade."""
        if self.cash_direction == "paid":
            return self.cash_amount or Decimal("0")
        return Decimal("0")

    @property
    def net_gain(self):
        """
        Net P&L of the trade:
          (value_received + cash you received) - (value_given + cash you paid)
        Positive = you came out ahead. Negative = you overpaid.
        """
        received_side = (self.received_value or Decimal("0")) + self.effective_cash_received
        given_side = (self.given_value or Decimal("0")) + self.effective_cash_paid
        return two_places(received_side - given_side)

    @property
    def roi(self):
        given = self.given_value or Decimal("0")
        paid = self.effective_cash_paid
        cost_basis = given + paid
        if not cost_basis:
            return None
        return two_places((self.net_gain / cost_basis) * 100)


class P2PGivenItem(models.Model):
    """One skin given away as part of a (possibly multi-item) P2P trade."""

    trade = models.ForeignKey(P2PTrade, on_delete=models.CASCADE, related_name="given_lines")
    inventory_item = models.ForeignKey(
        InventoryItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="p2p_given_lines",
        help_text="Skin from your inventory that you gave up.",
    )
    skin_name = models.CharField(max_length=200, blank=True)
    value = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Agreed value of this skin (for P&L tracking).",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.skin_name} (${self.value})"


class P2PReceivedItem(models.Model):
    """One skin received as part of a (possibly multi-item) P2P trade."""

    trade = models.ForeignKey(P2PTrade, on_delete=models.CASCADE, related_name="received_lines")
    skin_name = models.CharField(max_length=200)
    value = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Agreed value of this skin.",
    )
    # The new InventoryItem created for this received skin.
    inventory_item = models.OneToOneField(
        InventoryItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="p2p_received_line",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.skin_name} (${self.value})"
