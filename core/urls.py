from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("transactions/", views.transaction_list, name="transaction-list"),
    path("transactions/add/", views.transaction_add, name="transaction-add"),
    path("transactions/<int:pk>/edit/", views.transaction_edit, name="transaction-edit"),
    path("transactions/<int:pk>/delete/", views.transaction_delete, name="transaction-delete"),

    path("p2p/", views.p2p_list, name="p2p-list"),
    path("p2p/add/", views.p2p_add, name="p2p-add"),
    path("p2p/<int:pk>/edit/", views.p2p_edit, name="p2p-edit"),
    path("p2p/<int:pk>/delete/", views.p2p_delete, name="p2p-delete"),

    path("inventory/", views.inventory_list, name="inventory-list"),
    path("inventory/<int:pk>/update-estimate/", views.inventory_update_estimate, name="inventory-update-estimate"),

    path("calculator/", views.sell_calculator, name="sell-calculator"),

    path("reports/", views.reports, name="reports"),
]
