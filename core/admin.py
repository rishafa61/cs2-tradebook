from django.contrib import admin
from .models import InventoryItem, P2PGivenItem, P2PReceivedItem, P2PTrade, Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "type", "skin_name", "marketplace", "sell_price", "marketplace_fee", "net_profit")
    list_filter = ("type", "marketplace")
    search_fields = ("skin_name", "notes")

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("skin_name", "status", "purchase_price", "estimated_price", "purchase_date")
    list_filter = ("status",)
    search_fields = ("skin_name",)

class P2PGivenItemInline(admin.TabularInline):
    model = P2PGivenItem
    extra = 0

class P2PReceivedItemInline(admin.TabularInline):
    model = P2PReceivedItem
    extra = 0

@admin.register(P2PTrade)
class P2PTradeAdmin(admin.ModelAdmin):
    list_display = ("date", "given_skin_names", "received_skin_names", "given_value", "received_value", "cash_direction", "cash_amount", "net_gain")
    list_filter = ("cash_direction",)
    search_fields = ("notes", "given_lines__skin_name", "received_lines__skin_name")
    inlines = [P2PGivenItemInline, P2PReceivedItemInline]
