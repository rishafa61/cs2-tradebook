from django import forms
from django.db.models import Q
from django.forms import BaseFormSet, formset_factory

from .models import InventoryItem, P2PTrade, Transaction


class TransactionForm(forms.ModelForm):
    inventory_item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.none(),
        required=False,
        label="Which skin are you selling?",
    )

    class Meta:
        model = Transaction
        fields = [
            "date", "type", "skin_name", "marketplace",
            "buy_price", "sell_price", "marketplace_fee", "other_fee",
            "amount", "inventory_item", "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "type": forms.Select(attrs={"class": "form-select", "id": "id_type"}),
            "skin_name": forms.TextInput(attrs={"class": "form-control"}),
            "marketplace": forms.Select(attrs={"class": "form-select", "id": "id_marketplace"}),
            "buy_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "sell_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "id": "id_sell_price"}),
            "marketplace_fee": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "id": "id_marketplace_fee"}),
            "other_fee": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["inventory_item"].widget.attrs.update({"class": "form-select"})
        qs = InventoryItem.objects.filter(status="holding")
        if self.instance and self.instance.pk and self.instance.inventory_item_id:
            qs = InventoryItem.objects.filter(
                Q(status="holding") | Q(pk=self.instance.inventory_item_id)
            )
        self.fields["inventory_item"].queryset = qs

    def clean(self):
        cleaned = super().clean()
        t_type = cleaned.get("type")
        if t_type == "buy":
            if not cleaned.get("skin_name"):
                self.add_error("skin_name", "Skin name is required for a Buy.")
            if not cleaned.get("buy_price"):
                self.add_error("buy_price", "Buy price is required for a Buy.")
        elif t_type == "sell":
            if not cleaned.get("inventory_item"):
                self.add_error("inventory_item", "Select which inventory item you sold.")
            if not cleaned.get("sell_price"):
                self.add_error("sell_price", "Sell price is required for a Sell.")
        elif t_type in ("deposit", "withdraw"):
            if not cleaned.get("amount"):
                self.add_error("amount", "Amount is required for Deposits/Withdrawals.")
        return cleaned


class P2PTradeForm(forms.ModelForm):
    """Header fields only. The skins on each side are handled by the
    P2PGivenItemFormSet / P2PReceivedItemFormSet below, so a trade can
    involve multiple skins on either side (e.g. 2 items for 1)."""

    class Meta:
        model = P2PTrade
        fields = [
            "date",
            "cash_direction", "cash_amount",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "cash_direction": forms.Select(attrs={"class": "form-select", "id": "id_cash_direction"}),
            "cash_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "id": "id_cash_amount"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        direction = cleaned.get("cash_direction")
        amount = cleaned.get("cash_amount")
        if direction in ("received", "paid") and not amount:
            self.add_error("cash_amount", "Enter the cash amount for this trade.")
        if direction == "none":
            cleaned["cash_amount"] = None
        return cleaned


class P2PGivenItemForm(forms.Form):
    """One row: a skin from inventory being given away, plus its agreed value."""

    inventory_item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.none(),
        required=False,
        label="Skin",
        widget=forms.Select(attrs={"class": "form-select p2p-given-select"}),
    )
    value = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False,
        label="Agreed value",
        widget=forms.NumberInput(attrs={"class": "form-control p2p-value", "step": "0.01", "min": "0"}),
    )

    def __init__(self, *args, inventory_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        if inventory_qs is not None:
            self.fields["inventory_item"].queryset = inventory_qs

    def clean(self):
        cleaned = super().clean()
        item = cleaned.get("inventory_item")
        value = cleaned.get("value")
        # Only enforce "both or neither" when the row isn't being left blank.
        if item and value is None:
            self.add_error("value", "Enter an agreed value for this skin.")
        if value is not None and not item:
            self.add_error("inventory_item", "Select which skin this value belongs to.")
        return cleaned


class BaseP2PGivenItemFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        seen_items = []
        has_one = False
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if self.can_delete and self._should_delete_form(form):
                continue
            item = form.cleaned_data.get("inventory_item")
            if not item:
                continue
            has_one = True
            if item.pk in seen_items:
                form.add_error("inventory_item", "This skin is already added to this trade.")
            seen_items.append(item.pk)
        if not has_one:
            raise forms.ValidationError("Add at least one skin you're giving away.")


class P2PReceivedItemForm(forms.Form):
    """One row: a skin being received, plus its agreed value."""

    skin_name = forms.CharField(
        max_length=200, required=False, label="Skin name",
        widget=forms.TextInput(attrs={"class": "form-control p2p-received-name"}),
    )
    value = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False,
        label="Agreed value",
        widget=forms.NumberInput(attrs={"class": "form-control p2p-value", "step": "0.01", "min": "0"}),
    )

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("skin_name")
        value = cleaned.get("value")
        if name and value is None:
            self.add_error("value", "Enter an agreed value for this skin.")
        if value is not None and not name:
            self.add_error("skin_name", "Enter the skin name for this value.")
        return cleaned


class BaseP2PReceivedItemFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        has_one = False
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if self.can_delete and self._should_delete_form(form):
                continue
            name = form.cleaned_data.get("skin_name")
            if name:
                has_one = True
        if not has_one:
            raise forms.ValidationError("Add at least one skin you're receiving.")


P2PGivenItemFormSet = formset_factory(
    P2PGivenItemForm, formset=BaseP2PGivenItemFormSet, extra=1, can_delete=True,
)
P2PReceivedItemFormSet = formset_factory(
    P2PReceivedItemForm, formset=BaseP2PReceivedItemFormSet, extra=1, can_delete=True,
)
