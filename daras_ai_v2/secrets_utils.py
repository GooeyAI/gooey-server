from __future__ import annotations

from daras_ai_v2.google_utils import get_google_auth_session

from google.cloud import secretmanager
from google.api_core.exceptions import NotFound


class GCPSecret:
    @staticmethod
    def _get_client():
        return secretmanager.SecretManagerServiceClient()

    @staticmethod
    def _get_project_resource_name():
        # for GCP
        _, project_id = get_google_auth_session()
        return f"projects/{project_id}"

    def __init__(self, secret_id: str):
        self.secret_id = secret_id

    @classmethod
    def create(cls, secret_id: str, secret_value: str) -> GCPSecret:
        client = cls._get_client()
        parent = cls._get_project_resource_name()

        secret = client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {
                    "replication": {
                        "automatic": {},
                    },
                },
            }
        )

        client.add_secret_version(
            request={
                "parent": secret.name,
                "payload": {"data": secret_value.encode("UTF-8")},
            }
        )

        return cls(secret_id=secret_id)

    def get(self) -> str:
        client = self._get_client()
        parent = self._get_project_resource_name()

        secret_name = f"{parent}/secrets/{self.secret_id}"
        secret = client.access_secret_version(request={"name": secret_name})
        return secret.payload.data.decode("UTF-8")

    def exists(self) -> bool:
        client = self._get_client()
        parent = self._get_project_resource_name()

        secret_name = f"{parent}/secrets/{self.secret_id}"
        try:
            client.get_secret(request={"name": secret_name})
            return True
        except NotFound:
            return False

    def update(self, secret_value: str) -> GCPSecret:
        client = self._get_client()
        parent = self._get_project_resource_name()

        # Update the secret
        secret_name = f"{parent}/secrets/{self.secret_id}"
        secret = client.get_secret(request={"name": secret_name})

        client.add_secret_version(
            request={
                "parent": secret.name,
                "payload": {"data": secret_value.encode("UTF-8")},
            }
        )

        return self

    def delete(self):
        client = self._get_client()
        parent = self._get_project_resource_name()

        secret_name = f"{parent}/secrets/{self.secret_id}"
        client.delete_secret(request={"name": secret_name})
