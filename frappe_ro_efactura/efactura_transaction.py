## efactura_transaction.py
import frappe
from frappe.model.document import Document
from frappe import _
import logging
from .xml_generator import XMLGenerator
from .anaf_client import ANAFClient
from .digital_signer import DigitalSigner
from frappe.utils import get_url_to_form, get_datetime, now_datetime
from frappe.utils.pdf import get_pdf
from frappe.utils.jinja import get_jenv

logger = logging.getLogger(__name__)

class EFacturaTransaction(Document):
    def validate(self):
        """Validate transaction before submission with proper state management"""
        if not self.invoice_link:
            frappe.throw(_("Sales Invoice link is mandatory"), title=_("Missing Reference"))
            
        if self.status == "Draft" and not self.xml_data:
            self.generate_initial_xml()
            self.validate_xml_structure()

    def before_save(self):
        """Enforce valid status transitions and set timestamps"""
        status_transitions = {
            "Draft": ["Submitted", "Processing", "Validation Failed"],
            "Processing": ["Submitted", "Failed"],
            "Validation Failed": ["Draft"],
            "Failed": ["Processing"]
        }
        
        if self._doc_before_save:
            previous_status = self._doc_before_save.status
            if self.status not in status_transitions.get(previous_status, []):
                frappe.throw(_("Invalid status transition from {0} to {1}").format(
                    previous_status, self.status
                ))

        if self.status == "Processing":
            self.submission_time = now_datetime()

    def generate_initial_xml(self):
        """Generate and validate initial XML with proper error containment"""
        try:
            invoice = frappe.get_doc("Sales Invoice", self.invoice_link)
            invoice.add_einvoice_metadata()  # Ensure custom fields exist
            
            generator = XMLGenerator()
            self.xml_data = generator.generate_ubl_21(invoice)
        except Exception as e:
            self.status = "Validation Failed"
            self.log_error(_("XML generation error: {0}").format(str(e)))
            frappe.throw(_("Failed to generate initial XML"), exc=e)

    def validate_xml_structure(self):
        """Validate XML with detailed error reporting"""
        try:
            XMLGenerator().validate_with_schematron(self.xml_data)
        except frappe.ValidationError as e:
            self.status = "Validation Failed"
            self.log_error(_("Schematron validation failed: {0}").format(e.message))
            raise

    def submit_to_anaf(self):
        """Main submission flow with enhanced error handling and state management"""
        try:
            if self.status in ["Submitted", "Processing"]:
                return

            self._pre_submission_checks()
            self._update_status("Processing")
            
            signed_xml = self._sign_xml()
            response = self._send_to_anaf(signed_xml)
            self._handle_anaf_response(response)
            
        except frappe.ValidationError as e:
            self._handle_failure("Validation Error", str(e))
        except Exception as e:
            self._handle_failure("System Error", str(e))
        finally:
            frappe.db.commit()

    def _pre_submission_checks(self):
        """Validate system state before submission"""
        if not self.xml_data:
            frappe.throw(_("XML content missing"), title=_("Submission Error"))
            
        settings = self._get_efactura_settings()
        if not settings.is_configured():
            frappe.throw(_("e-Factura settings not configured properly"))

    def _sign_xml(self) -> str:
        """Sign XML with error handling for crypto operations"""
        try:
            settings = self._get_efactura_settings()
            signer = DigitalSigner(
                certificate=settings.decrypted_certificate,
                private_key=settings.get_decrypted_private_key()
            )
            return signer.sign_xml(self.xml_data)
        except xmlsec.Error as e:
            self.log_error(_("XML signing failed: {0}").format(str(e)))
            frappe.throw(_("Digital signature error"), exc=e)
        except Exception as e:
            self.log_error(_("Certificate error: {0}").format(str(e)))
            frappe.throw(_("Security configuration error"), exc=e)

    def _send_to_anaf(self, signed_xml: str) -> dict:
        """Handle ANAF communication with timeout safeguards"""
        try:
            settings = self._get_efactura_settings()
            client = ANAFClient(settings)
            return client.send_xml(signed_xml)
        except Exception as e:
            self.log_error(_("ANAF communication error: {0}").format(str(e)))
            raise

    def _handle_anaf_response(self, response: dict):
        """Process API response with atomic updates"""
        if response.get("status") == "success":
            self._update_success_state(response)
        else:
            self._update_failure_state(response)
            
        self.save()

    def _update_success_state(self, response):
        """Handle successful submission state"""
        self.update({
            "anaf_uuid": response.get("uuid"),
            "anaf_response": frappe.as_json(response.get("details")),
            "status": "Submitted",
            "retry_count": 0,
            "last_success_date": now_datetime()
        })

    def _update_failure_state(self, response):
        """Handle failed submission state"""
        self.update({
            "status": "Failed",
            "anaf_response": frappe.as_json(response),
            "retry_count": (self.retry_count or 0) + 1,
            "last_failure_date": now_datetime()
        })
        
        if self.retry_count >= 3:
            self.add_comment("Info", _("Maximum retry attempts reached"))

    def retry_failed(self):
        """Retry logic with safety checks"""
        if self.status != "Failed":
            frappe.throw(_("Only failed transactions can be retried"))

        if self.retry_count >= 3:
            frappe.throw(_("Maximum retry attempts (3) reached"))

        self.submit_to_anaf()

    def generate_pdf(self):
        """Generate PDF using Jinja template with proper formatting"""
        try:
            invoice = frappe.get_doc("Sales Invoice", self.invoice_link)
            template = get_jenv().get_template("efactura_template.html")
            html = template.render({
                "invoice": invoice,
                "transaction": self,
                "nowdate": get_datetime().strftime("%d-%m-%Y")
            })
            
            pdf_content = get_pdf(html)
            file_doc = self._save_pdf_file(pdf_content)
            return get_url_to_form("File", file_doc.name)
        except Exception as e:
            self.log_error(_("PDF generation failed: {0}").format(str(e)))
            frappe.throw(_("PDF creation error"), exc=e)

    def _save_pdf_file(self, content):
        """Save PDF to private files with access control"""
        return frappe.get_doc({
            "doctype": "File",
            "file_name": f"{self.name}.pdf",
            "content": content,
            "attached_to_doctype": self.doctype,
            "attached_to_name": self.name,
            "is_private": 1
        }).insert(ignore_permissions=True)

    def _get_efactura_settings(self):
        """Get settings with proper error handling"""
        settings = frappe.get_single("EFacturaSettings")
        if not settings.is_configured():
            frappe.throw(_("Complete e-Factura settings first"))
        return settings

    def _update_status(self, new_status):
        """Atomic status update with timestamp"""
        self.status = new_status
        self.save()
        frappe.db.commit()  # Ensure immediate save for background jobs

    def _handle_failure(self, error_type, message):
        """Centralized failure handling"""
        self.status = "Failed"
        self.log_error(f"{error_type}: {message}")
        frappe.db.rollback()
        self.save()
        frappe.throw(_("Submission failed: {0}").format(message))

    def log_error(self, message: str):
        """Enhanced error logging"""
        logger.error(message, exc_info=True)
        frappe.log_error(
            title=_("e-Factura Transaction Error"),
            message=f"{self.name}: {message}",
            reference_doctype=self.doctype,
            reference_name=self.name
        )

@frappe.whitelist()
def submit_transaction(docname: str):
    """Background submission endpoint with lock mechanism"""
    doc = frappe.get_doc("EFactura Transaction", docname)
    if doc.status in ["Processing", "Submitted"]:
        return
        
    with frappe.document_lock(doc):
        doc.reload()
        doc.submit_to_anaf()

@frappe.whitelist()
def retry_transaction(docname: str):
    """Retry endpoint with concurrency control"""
    doc = frappe.get_doc("EFactura Transaction", docname)
    with frappe.document_lock(doc):
        doc.reload()
        doc.retry_failed()
