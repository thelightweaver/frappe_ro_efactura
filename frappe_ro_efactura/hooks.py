## hooks.py
import frappe
from frappe import _
from pathlib import Path

app_name = "frappe_ro_efactura"

custom_fields = {
    "Sales Invoice": [
        {
            "fieldname": "efactura_section",
            "label": _("e-Factura"),
            "fieldtype": "Section Break",
            "insert_after": "terms",
            "collapsible": 1
        },
        {
            "fieldname": "anaf_uuid",
            "label": _("ANAF UUID"),
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "efactura_section"
        },
        {
            "fieldname": "efactura_status",
            "label": _("Status"),
            "fieldtype": "Select",
            "options": "\nDraft\nSubmitted\nProcessing\nValidation Failed\nFailed",
            "read_only": 1,
            "insert_after": "anaf_uuid"
        },
        {
            "fieldname": "efactura_transaction",
            "label": _("Transaction"),
            "fieldtype": "Link",
            "options": "EFactura Transaction",
            "read_only": 1,
            "insert_after": "efactura_status"
        },
        {
            "fieldname": "efactura_remarks",
            "label": _("Remarks"),
            "fieldtype": "Small Text",
            "read_only": 1,
            "insert_after": "efactura_transaction"
        }
    ]
}

scheduled_events = {
    "cron": [
        {
            "event": "all",
            "cron": "*/10 * * * *",
            "method": "frappe_ro_efactura.efactura.retry_failed_submissions"
        }
    ]
}

doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js"
}

doctype_template = {
    "Sales Invoice": "frappe_ro_efactura/templates/integration_button.html"
}

doc_events = {
    "Sales Invoice": {
        "on_submit": "frappe_ro_efactura.efactura.trigger_einvoice_submission",
        "on_cancel": "frappe_ro_efactura.efactura.handle_invoice_cancellation"
    }
}

def after_install():
    """Initialize required documents and settings after app installation"""
    create_efactura_settings()
    add_default_schematron_files()

def create_efactura_settings():
    """Create EFacturaSettings singleton if not exists"""
    if frappe.db.exists("EFactura Settings", "EFactura Settings"):
        return
    
    settings = frappe.new_doc("EFactura Settings")
    settings.sandbox_mode = 1  # Enable sandbox by default
    settings.insert(ignore_permissions=True)
    frappe.db.commit()

def add_default_schematron_files():
    """Create default schema directory and placeholder file"""
    schemas_path = Path(frappe.get_app_path(app_name)) / "schemas"
    schemas_path.mkdir(parents=True, exist_ok=True)
    
    target_file = schemas_path / "eFactura.sch"
    if not target_file.exists():
        target_file.write_text("<!-- Add default Schematron rules here -->")
