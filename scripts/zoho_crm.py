import os
import django
import sys
import logging
import json
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
import requests
import json

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
ZOHO_BULK_FILE_UPLOAD_API = "https://www.zohoapis.com/crm/v2/upload"


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
                "display_name": {"zoho_field": "Last_Name"},
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
                "user.name": {"zoho_field": "Contact foreign key"},
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


class ZOHOSyncManager:
    def __init__(
        self,
        field_mapper: ConfigurableFieldMapper,
        batch_size: int = 100,
        max_retries: int = 3,
    ):
        """
        :param field_mapper: Configurable field mapping instance
        :param batch_size: Number of records to process in a single batch
        :param max_retries: Maximum retry attempts for failed operations
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.field_mapper = field_mapper
        self.batch_size = batch_size
        self.max_retries = max_retries

        # Track sync progress and state
        self.sync_state = {
            "start_time": datetime.now(),
            "total_users_processed": 0,
            "total_transactions_synced": 0,
            "failed_operations": [],
            "retry_count": 0,
        }

        # self._init_zoho_client()

    # def _init_zoho_client(self):
    #     Initialise ZOHO here

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
        # Build transaction query with optional date filtering
        transaction_query = AppUserTransaction.objects.all()
        if start_date:
            transaction_query = transaction_query.filter(created_at__gte=start_date)

        if end_date:
            transaction_query = transaction_query.filter(created_at__lte=end_date)

        # Filter for positive transactions if specified
        if positive_only:
            transaction_query = transaction_query.filter(amount__gt=0)

        # Process transactions in batches
        for batch_start in range(0, transaction_query.count(), self.batch_size):
            batch_transactions = transaction_query[
                batch_start : batch_start + self.batch_size
            ]

            for transaction in batch_transactions:
                try:
                    # Fetch or create user contact in ZOHO
                    user = transaction.user

                    # Map user data to ZOHO contact
                    contact_data = self.field_mapper.map_model_to_zoho(
                        user, mapping_type="contact_mapping"
                    )

                    # Find or create contact in ZOHO
                    try:
                        contact = self._find_or_create_contact(contact_data)
                    except Exception as contact_error:
                        self.logger.error(
                            f"Contact creation failed for user {user.id}: {contact_error}"
                        )
                        self.sync_state["failed_operations"].append(
                            {
                                "transaction_id": transaction.id,
                                "user_id": user.id,
                                "error": "Contact creation failed",
                            }
                        )
                        continue

                    # Map transaction to ZOHO Deal
                    try:
                        deal_data = self.field_mapper.map_model_to_zoho(
                            transaction, mapping_type="transaction_mapping"
                        )

                        # Add mandotary fields
                        deal_data["Deal_Name"] = (
                            f"{transaction.workspace} {transaction.reason_note()}"
                        )
                        deal_data["Stage"] = "Organic  Closed Won"
                        deal_data["Vertical"] = "Organic"
                        deal_data["Pipeline"] = "Organic Deals"
                        deal_data["Primary Workflow"] = "Unknown"

                        # Create Deal in ZOHO
                        response = requests.post(
                            ZOHO_DEAL_API,
                            headers=ZOHO_HEADERS,
                            json={"data": [deal_data]},
                        )
                        if response.status_code == 400:
                            raise Exception(response.text)

                        # Update sync statistics
                        self.sync_state["total_transactions_synced"] += 1
                        if dry_run:
                            print(f"Dry Run - Transaction {transaction.id}")
                            print(f"Transaction Data: {deal_data}")
                            print(f"User Contact Data: {contact_data}")
                            continue
                    except Exception as deal_error:
                        self.logger.error(
                            f"Deal creation failed for transaction {transaction.id}: {deal_error}"
                        )
                        self.sync_state["failed_operations"].append(
                            {
                                "transaction_id": transaction.id,
                                "user_id": user.id,
                                "error": "Deal creation failed",
                            }
                        )

                except Exception as general_error:
                    self.logger.error(
                        f"Sync failed for transaction {transaction.id}: {general_error}"
                    )
                    self.sync_state["failed_operations"].append(
                        {
                            "transaction_id": transaction.id,
                            "error": "General sync error",
                        }
                    )

        return self.sync_state

    def _find_or_create_contact(self, contact_data: Dict):
        """
        Find existing contact or create new in ZOHO

        :param contact_data: Mapped contact information
        :return: ZOHO contact record
        """
        email = contact_data.get("Email")
        if not email:
            raise ValueError("Email is required for contact creation")

        search_criteria = f"Email:equals:{email}"
        search_response = requests.get(
            f"{ZOHO_CONTACT_API}/search?criteria={search_criteria}",
            headers=ZOHO_HEADERS,
        )
        if search_response.status_code == 400:
            raise Exception(search_response.text)

        if search_response.status_code == 204:
            response = requests.post(
                ZOHO_CONTACT_API,
                headers={**ZOHO_HEADERS, "Content-Type": "application/json"},
                json={"data": [contact_data]},
            )
            return response
        else:
            search_response


def run_advanced_zoho_sync(positive_only: bool = True, dry_run: bool = False):
    """
    :param config_path: Path to custom mapping configuration
    :param positive_only: Sync only positive transactions
    :param dry_run: Preview sync without API calls
    """
    logging.basicConfig(level=logging.INFO)

    field_mapper = ConfigurableFieldMapper()
    sync_manager = ZOHOSyncManager(field_mapper)

    results = sync_manager.bulk_sync_transactions(
        positive_only=positive_only, dry_run=dry_run
    )

    print("ZOHO Sync Complete:")
    print(f"Users Processed: {results['total_users_processed']}")
    print(f"Transactions Synced: {results['total_transactions_synced']}")
    print(f"Failed Operations: {len(results['failed_operations'])}")

    if results["failed_operations"]:
        print("Detailed Failures:")
        for failure in results["failed_operations"]:
            print(json.dumps(failure, indent=2))


if __name__ == "__main__":
    run_advanced_zoho_sync()
