## __init__.py
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

__version__ = "1.0.0"

app_name = "frappe_ro_efactura"
app_title = "Romanian E-Factura"
app_publisher = "Your Company"
app_description = "ANAF e-Factura integration for Frappe/ERPNext"
app_icon = "icon-invoice"
app_color = "#2ecc71"
app_email = "contact@yourcompany.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_ro_efactura/css/frappe_ro_efactura.css"
# app_include_js = "/assets/frappe_ro_efactura/js/frappe_ro_efactura.js"

# Include custom code and hooks
# -----------------------------
after_install = "frappe_ro_efactura.hooks.after_install"
doc_events = "frappe_ro_efactura.hooks.doc_events"
scheduler_events = "frappe_ro_efactura.hooks.scheduled_events"
doctype_js = "frappe_ro_efactura.hooks.doctype_js"
custom_fields = "frappe_ro_efactura.hooks.custom_fields"

# Fixtures
# ----------
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "frappe_ro_efactura"]]},
    {"dt": "Client Script", "filters": [["module", "=", "frappe_ro_efactura"]]}
]

# Permissions
# -----------
# Grant website user access to specific doctypes
# website_permissions = {
#     "EFactura Transaction": ["read"]
# }
