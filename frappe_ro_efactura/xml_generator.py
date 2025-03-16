## xml_generator.py
```python
## xml_generator.py
from lxml import etree
from pathlib import Path
import frappe
import logging
from frappe import _

logger = logging.getLogger(__name__)

class XMLGenerator:
    def __init__(self):
        self.namespaces = {
            'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }
        self.schematron_path = Path(frappe.get_app_path('frappe_ro_efactura')) / 'schemas'

    def generate_ubl_21(self, invoice):
        """Generate UBL 2.1 compliant XML from SalesInvoice document"""
        root = etree.Element('ubl:Invoice', nsmap=self.namespaces)
        
        # Add basic invoice information
        self._add_element(root, 'cbc:ID', invoice.name)
        self._add_element(root, 'cbc:IssueDate', invoice.posting_date)
        self._add_element(root, 'cbc:DocumentCurrencyCode', invoice.currency)

        # Add parties with proper structure
        self._add_party(root, 'AccountingSupplierParty', invoice.company)
        self._add_party(root, 'AccountingCustomerParty', invoice.customer)

        # Add invoice lines
        for item in invoice.get('items', []):
            line = etree.SubElement(root, 'cac:InvoiceLine')
            self._add_element(line, 'cbc:ID', item.idx)
            item_root = etree.SubElement(line, 'cac:Item')
            self._add_element(item_root, 'cbc:Name', item.item_name)
            
            quantity = etree.SubElement(line, 'cbc:InvoicedQuantity', 
                                      attrib={'unitCode': item.get('uom', 'UNIT')})
            quantity.text = str(item.qty)

        # Add monetary totals
        monetary_total = etree.SubElement(root, 'cac:LegalMonetaryTotal')
        self._add_element(monetary_total, 'cbc:TaxExclusiveAmount', 
                         invoice.net_total, {'currencyID': invoice.currency})
        self._add_element(monetary_total, 'cbc:TaxInclusiveAmount', 
                         invoice.grand_total, {'currencyID': invoice.currency})

        return etree.tostring(root, pretty_print=True, encoding='utf-8', xml_declaration=True)

    def validate_with_schematron(self, xml_str):
        """Validate XML against ANAF Schematron rules"""
        schematron_file = self.schematron_path / 'eFactura.sch'
        if not schematron_file.exists():
            frappe.throw(_("Schematron rules file missing at: {0}").format(schematron_file))

        try:
            # Parse and prepare Schematron validator
            schematron = etree.Schematron(etree.parse(str(schematron_file)))
            doc = etree.fromstring(xml_str)
            
            if not schematron.validate(doc):
                report = schematron.error_log
                logger.error(f"Schematron validation failed: {report}")
                frappe.throw(_("XML validation failed: {0}").format(report.last_error))
            return True
        except etree.XMLSyntaxError as e:
            logger.error(f"XML syntax error: {str(e)}")
            frappe.throw(_("Invalid XML structure: {0}").format(str(e)))

    def _add_element(self, parent, tag, value, attrs=None):
        """Helper to create XML elements with text and attributes"""
        element = etree.SubElement(parent, tag)
        if attrs:
            for k, v in attrs.items():
                element.set(k, v)
        if value is not None:
            element.text = str(value)
        return element

    def _add_party(self, root, party_type, party):
        """Add structured party information with nested elements"""
        party_root = etree.SubElement(root, f'cac:{party_type}')
        party_element = etree.SubElement(party_root, 'cac:Party')
        self._add_element(party_element, 'cbc:Name', party)
        # Additional fields can be added here:
        # self._add_element(party_element, 'cbc:CompanyID', party.tax_id)
