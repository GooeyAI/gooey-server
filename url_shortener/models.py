import hashids
import pytz
from django.db import models, transaction, IntegrityError
from furl import furl

from app_users.models import AppUser
from bots.custom_fields import CustomURLField
from bots.models import Workflow, SavedRun
from daras_ai_v2 import settings
from daras_ai_v2.query_params import gooey_get_query_params
from daras_ai_v2.query_params_util import extract_query_params


class ShortenedURLQuerySet(models.QuerySet):
    def get_or_create_for_workflow(
        self, *, user: AppUser, url: str, workflow: Workflow
    ) -> tuple["ShortenedURL", bool]:
        surl, created = self.filter_first_or_create(url=url, user=user)
        _, run_id, uid = extract_query_params(gooey_get_query_params())
        surl.saved_runs.add(
            SavedRun.objects.get_or_create(
                workflow=workflow,
                run_id=run_id,
                uid=uid,
            )[0],
        )
        return surl, created

    def filter_first_or_create(self, defaults=None, **kwargs):
        """
        Look up an object with the given kwargs, creating one if necessary.
        Return a tuple of (object, created), where created is a boolean
        specifying whether an object was created.
        """
        # The get() needs to be targeted at the write database in order
        # to avoid potential transaction consistency problems.
        self._for_write = True
        try:
            return self.filter(**kwargs)[0], False
        except IndexError:
            params = self._extract_model_params(defaults, **kwargs)
            # Try to create an object using passed params.
            try:
                with transaction.atomic(using=self.db):
                    # params = dict(resolve_callables(params))
                    return self.create(**params), True
            except IntegrityError:
                try:
                    return self.filter(**kwargs)[0], False
                except IndexError:
                    pass
                raise

    def get_by_hashid(self, hashid: str) -> "ShortenedURL":
        try:
            obj_id = _hashids.decode(hashid)[0]
        except IndexError as e:
            raise self.model.DoesNotExist from e
        else:
            return self.get(id=obj_id)

    def to_df(self, tz=pytz.timezone(settings.TIME_ZONE)) -> "pd.DataFrame":
        import pandas as pd

        qs = self.all().prefetch_related("saved_run")
        rows = []
        for surl in qs[:1000]:
            surl: ShortenedURL
            rows.append(
                {
                    "ID": surl.id,
                    "URL": surl.url,
                    "SHORTENED_URL": surl.shortened_url(),
                    "CREATED_AT": surl.created_at.astimezone(tz).replace(tzinfo=None),
                    "UPDATED_AT": surl.updated_at.astimezone(tz).replace(tzinfo=None),
                    "SAVED_RUN": str(surl.saved_run),
                    "CLICKS": surl.clicks,
                    "MAX_CLICKS": surl.max_clicks,
                    "DISABLED": surl.disabled,
                }
            )
        df = pd.DataFrame.from_records(rows)
        return df


_hashids = hashids.Hashids(salt=settings.HASHIDS_SALT)


class ShortenedURL(models.Model):
    url = CustomURLField()

    user = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="shortened_urls",
        null=True,
        blank=True,
        default=None,
        help_text="The user that generated this shortened url",
    )

    saved_runs = models.ManyToManyField(
        "bots.SavedRun",
        related_name="shortened_urls",
        blank=True,
        help_text="The runs that are using this shortened url",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    clicks = models.IntegerField(
        default=0, help_text="The number of clicks on this url"
    )
    max_clicks = models.IntegerField(
        default=0,
        help_text="The maximum number of clicks allowed. Set to 0 for no limit.",
    )
    disabled = models.BooleanField(
        default=False, help_text="Disable this shortened url"
    )

    objects = ShortenedURLQuerySet.as_manager()

    def shortened_url(self) -> str:
        return str(furl(settings.APP_BASE_URL) / "2" / _hashids.encode(self.id))

    shortened_url.short_description = "Shortened URL"

    class Meta:
        ordering = ("-created_at",)
        get_latest_by = "created_at"
        verbose_name = "Shortened URL"

    def __str__(self):
        return self.shortened_url() + " -> " + self.url
