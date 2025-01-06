import os
import django
import sys
import logging
import json
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
import requests
import json
import csv
from collections import defaultdict
from typing import List, Dict, Optional, Any, Tuple
import tempfile

from django.db.models import Model

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_path)

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "daras_ai_v2.settings")
django.setup()

from app_users.models import AppUserTransaction, TransactionReason
from daras_ai_v2 import settings

ZOHO_CONTACT_API = "https://www.zohoapis.com/crm/v2/Contacts"
ZOHO_DEAL_API = "https://www.zohoapis.com/crm/v7/Deals"
ZOHO_HEADERS = {"Authorization": f"Bearer {settings.ZOHO_AUTH_CODE}"}
ZOHO_BULK_FILE_UPLOAD_API = "https://content.zohoapis.com/crm/v7/upload"


class ConfigurableFieldMapper:
    def __init__(self):
        """
        :param mapping_config_path: Path to JSON mapping configuration
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.mapping_config = self._load_mapping_config()

    def _load_mapping_config(self) -> Dict:
        """
        :param config_path: Path to configuration file
        :return: Mapping configuration dictionary
        """
        default_config = {
            "contact_mapping": {
                "uid": {"zoho_field": "Gooey User ID"},
                "django_appUser_url": {"zoho_field": "Gooey Admin Link"},
                "display_name": {"zoho_field": "Contact Name"},
                # "display_name": {"zoho_field": "Last_Name"},
                "email": {"zoho_field": "Email"},
                "phone_number": {
                    "zoho_field": "Phone",
                    "transformer": lambda phone: phone.as_international,
                },
                "is_anonymous": {"zoho_field": "Not synced"},
                "is_disabled": {"zoho_field": "Not synced"},
                "photo_url": {"zoho_field": "Contact Image"},
                "workspace.balance": {"zoho_field": "Not synced"},
                "created_at": {
                    "zoho_field": "Gooey Created Date",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
                "handle.name": {"zoho_field": "Gooey Handle"},
                "upgraded_from_anonymous_at": {
                    "zoho_field": "Registered date",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
                "banner_url": {"zoho_field": "Not synced"},
                "bio": {"zoho_field": "Description"},
                "company": {"zoho_field": "Company"},
                "github_username": {"zoho_field": "Not synced"},
                "website_url": {"zoho_field": "Personal URL"},
                "disable_rate_limits": {"zoho_field": "Not synced"},
            },
            "transaction_mapping": {
                "workspace.id": {"zoho_field": "Account foreign key"},
                "workspace.name": {"zoho_field": "Account Name"},
                "user.display_name": {"zoho_field": "Contact foreign key"},
                "invoice_id": {"zoho_field": "invoice_id"},
                "amount": {"zoho_field": "Amount"},
                "end_balance": {"zoho_field": "end_balance"},
                "payment_provider": {
                    "zoho_field": "Payment Provider",
                    "transformer": lambda provider: provider.name,
                },
                "reason": {"zoho_field": "reason"},
                "created_at": {
                    "zoho_field": "Payment_date",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
                "charged_amount": {"zoho_field": "Amount"},
                "plan": {"zoho_field": "plan"},
                "payment_provider_url": {
                    "zoho_field": "Link to Payment",
                    "transformer": lambda url: url(),
                },
            },
            "workspace_mapping": {
                "id": {"zoho_field": "Gooey Workspace ID"},
                "name": {"zoho_field": "Account Name"},
                "balance": {"zoho_field": "Balance"},
                "created_at": {
                    "zoho_field": "Created Date",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
            },
        }

        return default_config

    def _deep_merge(self, base: Dict, update: Dict):
        """
        :param base: Default configuration
        :param update: User-provided configuration
        """
        for key, value in update.items():
            if isinstance(value, dict):
                base[key] = self._deep_merge(base.get(key, {}), value)
            else:
                base[key] = value
        return base

    def map_model_to_zoho(
        self, model_instance: Model, mapping_type: str
    ) -> dict[str, Any]:
        """
        :param model_instance: Django model instance
        :param mapping_type: Type of mapping (contact or transaction)
        :return: Mapped ZOHO field dictionary
        """
        mapping_config = self.mapping_config.get(mapping_type, {})
        zoho_fields = {}

        for model_field, field_config in mapping_config.items():
            try:
                # Check if the field is callable (ends with '()')
                if model_field.endswith("()"):
                    method_name = model_field.rstrip("()")
                    value = getattr(model_instance, method_name, None)
                    if callable(value):
                        value = value()  # Call the method
                    else:
                        raise AttributeError(f"{method_name} is not callable")
                else:
                    # Get value from model
                    value = getattr(model_instance, model_field, None)

                # Apply transformation if specified
                zoho_field = field_config.get("zoho_field")
                transformer = field_config.get("transformer")

                if value is not None and zoho_field:
                    transformered_value = transformer(value) if transformer else value
                    zoho_fields[zoho_field] = transformered_value

            except Exception as e:
                self.logger.warning(f"Mapping error for {model_field}: {e}")

        return zoho_fields


class ZohoBulkUploader:
    def __init__(self, field_mapper: "ConfigurableFieldMapper", batch_size: int = 100):
        self.field_mapper = field_mapper
        self.batch_size = batch_size
        self.logger = logging.getLogger(self.__class__.__name__)

    def prepare_bulk_data(
        self, transactions: List[AppUserTransaction]
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """Prepares data for bulk upload, organizing contacts, accounts, and deals"""
        contacts = defaultdict(dict)  # Use email as key
        accounts = defaultdict(dict)  # Use workspace ID as key
        deals = []

        for transaction in transactions:
            # Prepare contact data
            contact_data = self.field_mapper.map_model_to_zoho(
                transaction.user, "contact_mapping"
            )
            contacts[contact_data["Email"]] = contact_data

            # Prepare account (workspace) data
            workspace_data = self.field_mapper.map_model_to_zoho(
                transaction.workspace, "workspace_mapping"
            )

            if workspace_data and transaction.workspace.is_personal:
                workspace_data["Account Name"] = (
                    f"{transaction.user.display_name} Personal Workspace"
                )

            accounts[transaction.workspace.id] = workspace_data

            # Prepare deal data
            deal_data = self.field_mapper.map_model_to_zoho(
                transaction, "transaction_mapping"
            )
            deal_data.update(
                {
                    "Deal_Name": f"{transaction.workspace} {transaction.reason_note()}",
                    "Stage": "Organic  Closed Won",
                    "Vertical": "Organic",
                    "Pipeline": "Organic Deals",
                    "Primary Workflow": "Unknown",
                    "Contact_Name": contact_data.get("Full_Name", ""),
                    "Email": contact_data.get("Email", ""),
                }
            )
            deals.append(deal_data)

        return list(contacts.values()), list(accounts.values()), deals

    def create_bulk_upload_file(self, records: List[Dict], module: str) -> str:
        """Creates CSV file for bulk upload"""
        if not records:
            return None

        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(temp_dir, f"{module}_{timestamp}.csv")

        fieldnames = list(records[0].keys())

        with open(csv_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        return csv_path

    def upload_bulk_file(self, file_path: str, module: str) -> Dict:
        """Uploads CSV file to ZOHO CRM"""
        with open(file_path, "rb") as file:
            files = {"file": (os.path.basename(file_path), file)}
            data = {"module": module, "operation": "insert"}

            response = requests.post(
                ZOHO_BULK_FILE_UPLOAD_API,
                headers={**ZOHO_HEADERS, "feature": "bulk-write"},
                files=files,
                data=data,
            )

            if response.status_code != 200:
                raise Exception(f"Bulk upload failed: {response.text}")

            return response.json()


class ZOHOSync:
    def __init__(
        self,
        batch_size: int = 100,
        max_retries: int = 3,
    ):
        """
        :param field_mapper: Configurable field mapping instance
        :param batch_size: Number of records to process in a single batch
        :param max_retries: Maximum retry attempts for failed operations
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.field_mapper = ConfigurableFieldMapper()
        self.bulk_uploader = ZohoBulkUploader(self.field_mapper)
        self.batch_size = batch_size

    def bulk_sync_transactions(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        positive_only: bool = True,
        dry_run: bool = False,
        test: bool = False,
    ):
        """
        :param start_date: Optional start date for transaction filtering
        :param end_date: Optional end date for transaction filtering
        :param positive_only: Sync only positive transactions
        :param dry_run: Preview sync without actual API calls

        :return: Sync statistics
        """
        stats = {"processed": 0, "successful": 0, "failed": 0, "errors": []}
        # Build transaction query with optional date filtering
        transaction_query = AppUserTransaction.objects.all()
        if start_date:
            transaction_query = transaction_query.filter(created_at__gte=start_date)

        if end_date:
            transaction_query = transaction_query.filter(created_at__lte=end_date)

        # Filter for positive transactions if specified
        if positive_only:
            transaction_query = transaction_query.filter(amount__gt=0)

        for batch_start in range(0, transaction_query.count(), self.batch_size):
            batch_transactions = transaction_query[
                batch_start : batch_start + self.batch_size
            ]

            try:
                contacts, accounts, deals = self.bulk_uploader.prepare_bulk_data(
                    batch_transactions
                )

                # Upload contacts
                if contacts:
                    contact_file = self.bulk_uploader.create_bulk_upload_file(
                        contacts, "Contacts"
                    )
                    if dry_run:
                        print(f"Contacts: {contacts}")
                    else:
                        self.bulk_uploader.upload_bulk_file(contact_file, "Contacts")

                # Upload accounts
                if accounts:
                    account_file = self.bulk_uploader.create_bulk_upload_file(
                        accounts, "Accounts"
                    )
                    if dry_run:
                        print(f"Accounts: {accounts}")
                    else:
                        self.bulk_uploader.upload_bulk_file(account_file, "Accounts")

                # Upload deals
                if deals:
                    deal_file = self.bulk_uploader.create_bulk_upload_file(
                        deals, "Deals"
                    )
                    if dry_run:
                        print(f"Deals: {deals}")
                    else:
                        self.bulk_uploader.upload_bulk_file(deal_file, "Deals")

                stats["successful"] += len(batch_transactions)

            except Exception as e:
                self.logger.error(f"Batch sync failed: {str(e)}")
                stats["failed"] += len(batch_transactions)
                stats["errors"].append({"batch_start": batch_start, "error": str(e)})

            stats["processed"] += len(batch_transactions)

        return stats


def run_optimized_sync(
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
):
    """Convenience function to run the sync"""
    sync_manager = ZOHOSync()
    results = sync_manager.bulk_sync_transactions(start_date, end_date)

    print(f"Sync completed:")
    print(f"Processed: {results['processed']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")

    if results["errors"]:
        print("\nErrors encountered:")
        for error in results["errors"]:
            print(f"Batch starting at {error['batch_start']}: {error['error']}")


if __name__ == "__main__":
    run_optimized_sync()
