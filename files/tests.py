from unittest.mock import patch, Mock

from django.test import TestCase, TransactionTestCase

from app_users.models import AppUser
from bots.models import SavedRun
from files.models import FileMetadata, UploadedFile
from workspaces.models import Workspace
from daras_ai.image_input import upload_file_from_bytes


class _FakeBucket:
    def __init__(self, name: str = "test-bucket"):
        self.name = name

    def blob(self, name: str):
        return _FakeBlob(self, name)


class _FakeBlob:
    def __init__(self, bucket: _FakeBucket, name: str):
        self.bucket = bucket
        self.name = name
        self.path = name
        self.public_url = f"https://storage.googleapis.com/{bucket.name}/{name}"
        self.etag = "etag-1"
        self.content_type = None
        self.size = None

    def upload_from_string(self, data: bytes, content_type: str | None = None):
        self.content_type = content_type
        self.size = len(data)

    def reload(self):
        if self.content_type is None:
            self.content_type = "application/octet-stream"
        if self.size is None:
            self.size = 0
        if self.etag is None:
            self.etag = "etag-1"


class UploadedFileUploadTests(TestCase):
    def setUp(self):
        self.user = AppUser.objects.create(uid="user-1", is_anonymous=False)
        self.workspace = Workspace.objects.create(
            name="Test Workspace", created_by=self.user
        )
        self.saved_run = SavedRun.objects.create(
            workspace=self.workspace,
            uid=self.user.uid,
        )

    def test_upload_helper_creates_metadata_and_uploaded_file(self):
        fake_bucket = _FakeBucket()
        with patch("daras_ai.image_input.gcs_bucket", return_value=fake_bucket):
            url = upload_file_from_bytes(
                "test.txt",
                b"hello world",
                "text/plain",
                workspace=self.workspace,
            )

        self.assertTrue(url.startswith("https://storage.googleapis.com/"))
        self.assertEqual(FileMetadata.objects.count(), 1)
        self.assertEqual(UploadedFile.objects.count(), 1)

        uploaded = UploadedFile.objects.first()
        self.assertEqual(uploaded.metadata.name, "test.txt")
        self.assertEqual(uploaded.metadata.mime_type, "text/plain")
        self.assertEqual(uploaded.metadata.total_bytes, len(b"hello world"))
        self.assertEqual(uploaded.workspace, self.workspace)
        self.assertIsNone(uploaded.user)
        self.assertFalse(uploaded.is_user_uploaded)

    def test_upload_helper_can_mark_user_uploaded(self):
        fake_bucket = _FakeBucket()
        with patch("daras_ai.image_input.gcs_bucket", return_value=fake_bucket):
            upload_file_from_bytes(
                "user.txt",
                b"hello world",
                "text/plain",
                workspace=self.workspace,
                user=self.user,
                is_user_uploaded=True,
            )

        uploaded = UploadedFile.objects.get()
        self.assertTrue(uploaded.is_user_uploaded)

    def test_upload_helper_resolves_saved_run_context_to_user_and_workspace(self):
        fake_bucket = _FakeBucket()
        with (
            patch("daras_ai.image_input.gcs_bucket", return_value=fake_bucket),
            patch("celeryapp.tasks.get_running_saved_run", return_value=self.saved_run),
        ):
            upload_file_from_bytes("audio.wav", b"abc", "audio/wav")

        uploaded = UploadedFile.objects.get()
        self.assertEqual(uploaded.user, self.user)
        self.assertEqual(uploaded.workspace, self.workspace)


class UploadedFileDeleteSignalTests(TransactionTestCase):
    def test_uploaded_file_delete_triggers_blob_delete(self):
        metadata = FileMetadata.objects.create(
            name="file.txt",
            etag="etag-2",
            mime_type="text/plain",
            total_bytes=5,
        )
        uploaded = UploadedFile.objects.create(
            metadata=metadata,
            f_url="https://storage.googleapis.com/test-bucket/path/file.txt",
            bucket_name="test-bucket",
            object_name="path/file.txt",
        )

        fake_blob = Mock()
        fake_bucket = Mock()
        fake_bucket.blob.return_value = fake_blob

        with patch("files.signals.storage.bucket", return_value=fake_bucket):
            uploaded.delete()

        fake_blob.delete.assert_called_once()

    def test_missing_blob_delete_is_non_fatal(self):
        from google.api_core.exceptions import NotFound

        metadata = FileMetadata.objects.create(
            name="file.txt",
            etag="etag-3",
            mime_type="text/plain",
            total_bytes=5,
        )
        uploaded = UploadedFile.objects.create(
            metadata=metadata,
            f_url="https://storage.googleapis.com/test-bucket/path/file.txt",
            bucket_name="test-bucket",
            object_name="path/file.txt",
        )

        fake_blob = Mock()
        fake_blob.delete.side_effect = NotFound("missing")
        fake_bucket = Mock()
        fake_bucket.blob.return_value = fake_blob

        with patch("files.signals.storage.bucket", return_value=fake_bucket):
            uploaded.delete()
