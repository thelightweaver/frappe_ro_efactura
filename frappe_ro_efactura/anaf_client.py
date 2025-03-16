## anaf_client.py
import requests
import frappe
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import RequestException, Timeout
from frappe import _
from frappe.utils import cint, get_bench_path
from pathlib import Path
import tempfile
import os

logger = logging.getLogger(__name__)
RETRY_STATUS_CODES = [500, 502, 503, 504]

class ANAFClient:
    def __init__(self, settings_doc):
        """Initialize ANAF API client with connection settings"""
        self.settings = settings_doc
        self.config = self.settings.configure_connection()
        self.session = self._configure_session()
        self._setup_authentication()

    def _configure_session(self):
        """Create requests session with retry logic"""
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=["POST", "GET"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        return session

    def _setup_authentication(self):
        """Configure authentication based on settings"""
        if self.config['auth_type'] == 'Certificate':
            self._handle_certificate_auth()
        elif self.config['auth_type'] == 'OAuth2':
            self._handle_oauth_auth()
        else:
            frappe.throw(_("Invalid authentication method configured"))

    def _handle_certificate_auth(self):
        """Configure client certificate authentication"""
        cert_content = self.config.get('certificate')
        if not cert_content:
            frappe.throw(_("Client certificate missing in configuration"))

        try:
            # Write certificate to temporary file
            with tempfile.NamedTemporaryFile(delete=False) as cert_file:
                cert_file.write(cert_content.encode())
                self.cert_path = cert_file.name
        except IOError as e:
            frappe.throw(_("Failed to process certificate: {0}").format(str(e)))

    def _handle_oauth_auth(self):
        """Configure OAuth2 authentication flow"""
        oauth_creds = self.config.get('oauth_creds')
        if not oauth_creds:
            frappe.throw(_("OAuth credentials missing in configuration"))

        token_url = f"{self.config['api_url']}/oauth2/token"
        try:
            response = requests.post(
                token_url,
                data={
                    'client_id': oauth_creds['client_id'],
                    'client_secret': oauth_creds['client_secret'],
                    'grant_type': 'client_credentials'
                }
            )
            response.raise_for_status()
            token_data = response.json()
            self.session.headers.update({
                'Authorization': f"Bearer {token_data['access_token']}"
            })
        except RequestException as e:
            logger.error(f"OAuth2 Token Error: {str(e)}")
            frappe.throw(_("ANAF OAuth2 authentication failed"))

    def send_xml(self, xml_data):
        """Submit signed XML to ANAF API with proper error handling"""
        endpoint = f"{self.config['api_url']}/upload"
        try:
            response = self.session.post(
                endpoint,
                data=xml_data,
                headers={'Content-Type': 'application/xml'},
                cert=self.cert_path if self.config['auth_type'] == 'Certificate' else None,
                timeout=10
            )
            response.raise_for_status()
            return self._parse_response(response.json())
        except Timeout:
            logger.error("ANAF API timeout occurred")
            frappe.throw(_("ANAF API request timed out"))
        except RequestException as e:
            self._log_and_handle_error(e, "XML submission failed")
        finally:
            if hasattr(self, 'cert_path'):
                self._cleanup_certificate()

    def check_status(self, uuid):
        """Check invoice status by UUID with retry logic"""
        endpoint = f"{self.config['api_url']}/status/{uuid}"
        try:
            response = self.session.get(endpoint, timeout=8)
            response.raise_for_status()
            return self._parse_response(response.json())
        except RequestException as e:
            self._log_and_handle_error(e, "Status check failed")
            return {'status': 'error', 'error': str(e)}

    def _parse_response(self, response_data):
        """Parse and normalize ANAF API response"""
        if cint(response_data.get('success')):
            return {
                'status': 'success',
                'uuid': response_data.get('correlationId'),
                'details': response_data.get('processedData')
            }
        
        error_msg = response_data.get('errorMessage', _("Unknown API error"))
        return {
            'status': 'error',
            'error': error_msg,
            'code': response_data.get('errorCode', 'E500')
        }

    def _log_and_handle_error(self, error, context):
        """Centralized error logging and handling"""
        logger.error(f"{context}: {str(error)}", exc_info=True)
        frappe.log_error(
            title=_("ANAF Communication Error"),
            message=f"{context}: {str(error)}"
        )
        frappe.throw(_("ANAF API Error: {0}").format(context))

    def _cleanup_certificate(self):
        """Clean up temporary certificate files"""
        try:
            if os.path.exists(self.cert_path):
                os.unlink(self.cert_path)
        except Exception as e:
            logger.warning(f"Certificate cleanup failed: {str(e)}")
