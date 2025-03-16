## efactura.py
import frappe
from frappe import _
from frappe.utils.background_jobs import enqueue
from frappe.model.document import Document
import logging
from .efactura_transaction import EFacturaTransaction

logger = logging.getLogger(__name__)

def trigger_einvoice_submission(doc, method):
    """Automatically create and submit e-invoice transaction when Sales Invoice is submitted"""
    try:
        if _should_skip_einvoice(doc):
            return

        transaction = _create_transaction_doc(doc)
        _update_invoice_fields(doc, transaction)
        _enqueue_submission(transaction.name)

    except Exception as e:
        logger.error(_("E-Invoice submission failed for {0}: {1}").format(doc.name, str(e)), exc_info=True)
        frappe.throw(_("E-Invoice initialization failed. See logs for details."), exc=e)

def retry_failed_submissions():
    """Scheduled job to automatically retry failed submissions with exponential backoff"""
    failed_transactions = frappe.get_all(
        "EFactura Transaction",
        filters={"status": "Failed", "retry_count": ["<", 3]},
        pluck="name"
    )
    
    for docname in failed_transactions:
        enqueue(
            "frappe_ro_efactura.efactura._retry_transaction_job",
            queue="long",
            docname=docname,
            enqueue_after_commit=True
        )

def handle_invoice_cancellation(doc, method):
    """Prevent cancellation of invoices with active e-invoice transactions"""
    if not doc.efactura_transaction:
        return

    transaction = frappe.get_doc("EFactura Transaction", doc.efactura_transaction)
    if transaction.status == "Submitted":
        frappe.throw(_("Cannot cancel invoice with active e-invoice submission. Revoke ANAF submission first."))
    
    transaction.db_set("status", "Cancelled")
    doc.db_set("efactura_status", "Cancelled")

@frappe.whitelist()
def submit_transaction(docname: str):
    """Public endpoint for transaction submission with lock checking"""
    doc = frappe.get_doc("EFactura Transaction", docname)
    if doc.status in ["Processing", "Submitted"]:
        return

    with frappe.document_lock(doc):
        doc.reload()
        doc.submit_to_anaf()

@frappe.whitelist()
def retry_transaction(docname: str):
    """Public endpoint for transaction retries with concurrency control"""
    doc = frappe.get_doc("EFactura Transaction", docname)
    with frappe.document_lock(doc):
        doc.reload()
        doc.retry_failed()

def _should_skip_einvoice(doc) -> bool:
    """Determine if e-invoice should be skipped for this document"""
    return doc.is_return or doc.efactura_transaction or doc.docstatus != 1

def _create_transaction_doc(doc) -> Document:
    """Create new EFacturaTransaction document"""
    transaction = frappe.new_doc("EFactura Transaction")
    transaction.update({
        "invoice_link": doc.name,
        "status": "Draft"
    })
    transaction.insert(ignore_permissions=True)
    return transaction

def _update_invoice_fields(doc, transaction) -> None:
    """Update Sales Invoice with transaction reference"""
    doc.db_set({
        "efactura_transaction": transaction.name,
        "efactura_status": "Draft"
    })

def _enqueue_submission(docname: str) -> None:
    """Queue submission job with priority handling"""
    enqueue(
        "frappe_ro_efactura.efactura.submit_transaction",
        queue="short",
        docname=docname,
        timeout=300,
        enqueue_after_commit=True
    )

def _retry_transaction_job(docname: str) -> None:
    """Wrapper for safe retry execution"""
    try:
        retry_transaction(docname)
    except Exception as e:
        logger.error(_("Retry failed for {0}: {1}").format(docname, str(e)), exc_info=True)
