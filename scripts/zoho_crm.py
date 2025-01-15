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
import zipfile
import tempfile

from django.db.models import Model

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_path)

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "daras_ai_v2.settings")
django.setup()

from app_users.models import AppUserTransaction, PaymentProvider, TransactionReason
from daras_ai_v2 import settings

ZOHO_CONTACT_API = "https://www.zohoapis.com/crm/v2/Contacts"
ZOHO_DEAL_API = "https://www.zohoapis.com/crm/v7/Deals"
ZOHO_HEADERS = {"Authorization": f"Bearer {settings.ZOHO_AUTH_CODE}"}
ZOHO_BULK_FILE_UPLOAD_API = "https://content.zohoapis.com/crm/v7/upload"
ZOHO_BULK_CREATE_JOB = "https://www.zohoapis.com/crm/bulk/v7/write"
ZOHO_ORG_ID = settings.ZOHO_ORG_ID


def get_field_mappings(module: str) -> List[Dict]:
    field_mappings = {
        "Deals": [
            {"api_name": "Layout", "default_value": {"value": "6093802000000498176"}},
            {"api_name": "id", "index": 0},
            {"api_name": "Invoice_ID", "index": 1},
            {"api_name": "Account_Lookup", "index": 2, "find_by": "id"},
            {"api_name": "Contact_Lookup", "index": 3, "find_by": "id"},
            {"api_name": "Account_Title", "index": 4},
            {"api_name": "Contact_Email", "index": 5},
            {"api_name": "Amount", "index": 6},
            {"api_name": "End_Balance", "index": 7},
            {"api_name": "Payment_Provider", "index": 8},
            {"api_name": "Reason", "index": 9},
            {"api_name": "Closing_Date", "index": 10, "format": "yyyy-MM-dd"},
            {"api_name": "Link_to_Payment", "index": 11},
            {"api_name": "Currency_Type", "index": 12},
            {"api_name": "Deal_Name", "index": 13},
            {"api_name": "Stage", "index": 14},
            {"api_name": "Vertical", "index": 15},
            {"api_name": "Pipeline", "index": 16},
            {"api_name": "Type", "index": 17},
            {"api_name": "Primary_Workflow", "index": 18},
        ],
        "Contacts": [
            {"api_name": "id", "index": 0},
            {"api_name": "Gooey_User_ID", "index": 1},
            # {"api_name": "Gooey_Admin_Link", "index": 2},
            {"api_name": "Contact_Name", "index": 3},
            {"api_name": "Last_Name", "index": 4},
            {"api_name": "Email", "index": 5},
            {"api_name": "Phone", "index": 6},
            {"api_name": "Not_Synced", "index": 7},
            {"api_name": "Contact_Image", "index": 8},
            {"api_name": "Gooey_Created_Date", "index": 9, "format": "yyyy-MM-dd"},
            {"api_name": "Gooey_Handle", "index": 10},
            {"api_name": "Registered_Date", "index": 11, "format": "yyyy-MM-dd"},
            {"api_name": "Description", "index": 12},
            {"api_name": "Company", "index": 13},
            {"api_name": "Personal_Url", "index": 14},
        ],
        "Accounts": [
            {"api_name": "id", "index": 0},
            {"api_name": "Account_Name", "index": 1},
            {"api_name": "Balance", "index": 2},
            {"api_name": "Is_Paying", "index": 3},
            {"api_name": "Gooey_Admin_Link", "index": 4},
            {"api_name": "Created_Date", "index": 5, "format": "yyyy-MM-dd"},
            {"api_name": "Updated_At", "index": 5, "format": "yyyy-MM-dd"},
        ],
    }
    return field_mappings.get(module, [])


def get_zoho_module_name(module: str) -> str:
    """
    :param module: Zoho CRM module name
    :return: Zoho CRM module API name
    """
    module_names = {
        "Contacts": "Contacts",
        "Accounts": "Accounts",
        "Deals": "Deals",
    }
    return module_names.get(module, "Contacts")


def get_unique_field(module: str) -> str:
    """
    :param module: Zoho CRM module name
    :return: Unique field name for the specified module
    """
    unique_fields = {
        "Contacts": "id",
        "Accounts": "id",
        "Deals": "id",
    }
    return unique_fields.get(module, "ID")


class ConfigurableFieldMapper:
    def __init__(self):
        """
        :param mapping_config_path: Path to JSON mapping configuration
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.mapping_config = self._load_mapping_config()

    def _load_mapping_config(self) -> Dict:
        """
        :return: Mapping configuration dictionary
        """
        default_config = {
            "contact_mapping": {
                "id": {"db_key": "id"},
                "Gooey_User_ID": {"db_key": "uid"},
                "Gooey_Admin_Link": {
                    "db_key": "django_appUser_url",
                    "transformer": lambda url: url(),
                },
                "Contact_Name": {"db_key": "display_name"},
                "Last_Name": {
                    "db_key": "display_name",
                    "transformer": lambda name: name.split(" ")[-1],
                },
                "Email": {"db_key": "email"},
                "Phone": {
                    "db_key": "phone_number",
                    "transformer": lambda phone: phone.as_international,
                },
                "Not_Synced": {"db_key": "is_anonymous"},
                "Contact_Image": {"db_key": "photo_url"},
                "Gooey_Created_Date": {
                    "db_key": "created_at",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
                "Gooey_Handle": {"db_key": "handle.name"},
                "Registered_Date": {
                    "db_key": "upgraded_from_anonymous_at",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
                "Description": {"db_key": "bio"},
                "Company": {"db_key": "company"},
                "Personal_URL": {"db_key": "website_url"},
            },
            "transaction_mapping": {
                "id": {"db_key": "id"},
                "Invoice_ID": {"db_key": "invoice_id"},
                "Account_Lookup": {
                    "db_key": "workspace",
                    "transformer": lambda workspace: workspace.id,
                },
                "Contact_Lookup": {
                    "db_key": "user",
                    "transformer": lambda user: user.id,
                },
                "Account_Name": {"db_key": "workspace"},
                "Contact_Email": {
                    "db_key": "user",
                    "transformer": lambda user: user.email,
                },
                "Amount": {"db_key": "amount"},
                "End_Balance": {"db_key": "end_balance"},
                "Payment_Provider": {
                    "db_key": "payment_provider",
                    "transformer": lambda provider: PaymentProvider(provider).name,
                },
                "Reason": {
                    "db_key": "reason",
                    "transformer": lambda reason: TransactionReason(reason).name,
                },
                "Closing_Date": {
                    "db_key": "created_at",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
                "Link_to_Payment": {
                    "db_key": "payment_provider_url",
                    "transformer": lambda url: url(),
                },
                "Currency": {"db_key": "currency", "default": "USD"},
            },
            "workspace_mapping": {
                "id": {"db_key": "id"},
                "Account_Name": {"db_key": "name"},
                "Account_Image": {"db_key": "photo_url"},
                "Balance": {"db_key": "balance"},
                "Is_Paying": {"db_key": "is_paying"},
                "Gooey_Admin_Link": {
                    "db_key": "django_workspace_url",
                    "transformer": lambda url: url(),
                },
                "Created_Date": {
                    "db_key": "created_at",
                    "transformer": lambda date: date.strftime("%Y-%m-%d"),
                },
                "Updated_At": {
                    "db_key": "updated_at",
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

        for zoho_field, field_config in mapping_config.items():
            try:
                db_key = field_config.get("db_key")
                transformer = field_config.get("transformer")

                value = getattr(model_instance, db_key, None)

                # Apply transformation if specified
                if value is not None:
                    zoho_fields[zoho_field] = (
                        transformer(value) if transformer else value
                    )
                else:
                    zoho_fields[zoho_field] = field_config.get("default") or "None"

            except Exception as e:
                self.logger.warning(f"Mapping error for {zoho_field}: {e}")

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
            contact_data["Account_Lookup"] = transaction.workspace.id
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
                    "Deal_Name": f"${transaction.amount} {transaction.workspace} {transaction.reason_note()}",
                    "Stage": "Organic  Closed Won",
                    "Vertical": "Organic",
                    "Pipeline": "Organic Deals",
                    "Type": "Organic - Other",
                    "Primary_Workflow": "Unknown",
                }
            )
            deals.append(deal_data)

        return list(contacts.values()), list(accounts.values()), deals

    def create_bulk_upload_file(
        self, records: List[Dict], module: str, filename: str
    ) -> str:
        """Creates CSV file for bulk upload"""
        if not records:
            return None

        temp_dir = tempfile.gettempdir()
        csv_path = os.path.join(temp_dir, f"{module}_{filename}.csv")

        fieldnames = list(records[0].keys())

        with open(csv_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        return csv_path

    def upload_bulk_file(self, file_path: str) -> Dict:
        zip_path = f"{file_path}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(file_path, arcname=os.path.basename(file_path))

        with open(zip_path, "rb") as file:
            files = {"file": (os.path.basename(zip_path), file)}

            response = requests.post(
                ZOHO_BULK_FILE_UPLOAD_API,
                headers={
                    **ZOHO_HEADERS,
                    "feature": "bulk-write",
                    "X-CRM-ORG": ZOHO_ORG_ID,
                },
                files=files,
            )

            if response.status_code != 200:
                raise Exception(f"Bulk upload failed: {response}")

            response_data = response.json()
            if (
                "details" not in response_data
                or "file_id" not in response_data["details"]
            ):
                raise Exception(
                    f"Failed to retrieve file_id from upload response: {response_data}"
                )

            return response_data["details"]

    def create_bulk_upload_job(
        self, file_ids: List[str], operation: str = "upsert"
    ) -> Dict:
        deal_file_id, account_file_id, contact_file_id = file_ids
        modules = ["Accounts", "Contacts", "Deals"]
        file_id_map = {
            "Accounts": account_file_id,
            "Contacts": contact_file_id,
            "Deals": deal_file_id,
        }

        results = []

        for module in modules:
            data = {
                "operation": operation,
                "resource": [
                    {
                        "type": "data",
                        "module": {"api_name": module},
                        "file_id": file_id_map[module],
                        "find_by": get_unique_field(module),
                        "field_mappings": get_field_mappings(module),
                    }
                ],
            }

            try:
                response = requests.post(
                    ZOHO_BULK_CREATE_JOB,
                    headers={**ZOHO_HEADERS},
                    json=data,
                )

                if response.status_code != 201:
                    raise Exception(
                        f"Bulk upload job creation failed for {module}: {response.text}"
                    )

                results.append({"module": module, "response": response.json()})

            except Exception as e:
                print(f"Error creating bulk upload job for {module}: {str(e)}")
                raise

        return results

    def process_bulk_upload(self, files: []) -> Dict:
        if not files:
            raise Exception("No files provided for bulk upload.")

        deal_file, account_file, contact_file = files
        account_file_id = self.upload_bulk_file(account_file).get("file_id")
        deal_file_id = self.upload_bulk_file(deal_file).get("file_id")
        contact_file_id = self.upload_bulk_file(contact_file).get("file_id")

        print(f"Account File ID: {account_file_id}")
        print(f"Deal File ID: {deal_file_id}")
        print(f"Contact File ID: {contact_file_id}")

        for file_id in account_file_id, deal_file_id, contact_file_id:
            if not file_id:
                raise Exception("File upload did not return a valid file_id.")

        self.logger.info(f"File uploaded successfully. File ID: {file_id}")

        self.logger.info(f"Creating bulk upload job")
        job_response = self.create_bulk_upload_job(
            [deal_file_id, account_file_id, contact_file_id],
            operation="upsert",
        )

        self.logger.info(
            f"Bulk upload job created successfully. Job Details: {job_response}"
        )
        return job_response


class ZOHOSync:

    def __init__(
        self,
        batch_size: int = 50,
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.field_mapper = ConfigurableFieldMapper()
        self.bulk_uploader = ZohoBulkUploader(self.field_mapper)
        self.batch_size = batch_size

    def bulk_sync_transactions(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        positive_only: bool = True,
        limit: int | None = None,
    ):
        stats = {"processed": 0, "successful": 0, "failed": 0, "errors": []}
        # Build transaction query with optional date filtering
        transaction_query = AppUserTransaction.objects.all().order_by("created_at")

        # @TODO filter from wrt batch size from created_at like pagination ( paginate_queryset )

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
            # stop if above limit
            if limit and batch_start >= limit:
                print("Limit reached. Stopping sync.")
                break

            batch_label = f"{batch_start}-{batch_start + self.batch_size}"

            try:
                contacts, accounts, deals = self.bulk_uploader.prepare_bulk_data(
                    batch_transactions
                )

                if accounts:
                    account_file = self.bulk_uploader.create_bulk_upload_file(
                        accounts, "Accounts", batch_label
                    )

                if contacts:
                    contact_file = self.bulk_uploader.create_bulk_upload_file(
                        contacts, "Contacts", batch_label
                    )

                if deals:
                    deal_file = self.bulk_uploader.create_bulk_upload_file(
                        deals, "Deals", batch_label
                    )

                stats["successful"] += len(batch_transactions)

                print(f"{batch_label} Deals CSV: {deal_file}")
                print(f"{batch_label} Contacts CSV: {contact_file}")
                print(f"{batch_label} Accounts CSV: {account_file}")

                if deal_file:
                    upload_response = self.bulk_uploader.process_bulk_upload(
                        [deal_file, account_file, contact_file]
                    )
                    print(f"Deals upload response: {upload_response}")

            except Exception as e:
                self.logger.error(f"Batch sync failed: {str(e)}")
                stats["failed"] += len(batch_transactions)
                stats["errors"].append({"batch_start": batch_start, "error": str(e)})

            stats["processed"] += len(batch_transactions)

        return stats

    def _get_user_confirmation(self, label: str) -> bool:
        f"Are you sure you want to proceed with the upload for batch {label}?"
        while True:
            user_input = (
                input("Proceed with uploading this batch? (yes/no): ").strip().lower()
            )
            if user_input in {"yes", "y"}:
                return True
            elif user_input in {"no", "n"}:
                print("Skipping this batch.")
                return False
            else:
                print("Invalid input. Please type 'yes' or 'no'.")


def run_optimized_sync(
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
):
    """Convenience function to run the sync"""
    sync_manager = ZOHOSync()
    results = sync_manager.bulk_sync_transactions(start_date, end_date, limit=50)

    print(f"Sync completed:")
    print(f"Processed: {results['processed']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")

    if results["errors"]:
        print("\nErrors encountered:")
        for error in results["errors"]:
            print(f"Batch starting at {error['batch_start']}: {error['error']}")


if __name__ == "__main__":
    argv = sys.argv[1:]

    # get args from command line and convert date string to datetime object
    start_date = datetime.strptime(argv[0], "%Y-%m-%d") if argv else None
    run_optimized_sync()
