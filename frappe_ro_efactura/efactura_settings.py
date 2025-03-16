## efactura_settings.py
import frappe
from frappe.model.document import Document
from frappe import _

class EFacturaSettings(Document):
    def validate(self):
        """Validate authentication credentials based on selected method"""
        self.validate_authentication_credentials()

    def validate_authentication_credentials(self):
        """Ensure required fields for each authentication method"""
        if self.auth_method == "Certificate":
            if not self.client_certificate:
                frappe.throw(_("Client Certificate is required for certificate authentication"))
        elif self.auth_method == "OAuth2":
            if not self.oauth_client_id or not self.oauth_client_secret:
                frappe.throw(_("OAuth Client ID and Secret are required for OAuth2 authentication"))
        else:
            frappe.throw(_("Invalid authentication method selected"))

    def configure_connection(self):
        """Prepare connection parameters for ANAF API client"""
        return {
            "api_url": self.anaf_api_url,
            "auth_type": self.auth_method,
            "certificate": self.decrypted_certificate if self.auth_method == "Certificate" else None,
            "oauth_creds": self.oauth_credentials if self.auth_method == "OAuth2" else None
        }

    @property
    def anaf_api_url(self):
        """Get appropriate API URL based on environment"""
        return (
            "https://api.anaf.ro/test/FCTEL/rest" 
            if self.sandbox_mode 
            else "https://api.anaf.ro/prod/FCTEL/rest"
        )

    @property
    def decrypted_certificate(self):
        """Get decrypted client certificate for authentication"""
        return frappe.get_decrypted_password(
            self.doctype, 
            self.name, 
            'client_certificate'
        )

    @property
    def oauth_credentials(self):
        """Get OAuth credentials as a secure dictionary"""
        return {
            "client_id": self.oauth_client_id,
            "client_secret": frappe.get_decrypted_password(
                self.doctype,
                self.name,
                'oauth_client_secret'
            )
        }
