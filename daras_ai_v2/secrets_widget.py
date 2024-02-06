from textwrap import dedent

from app_users.models import AppUser
from bots.models import UserSecret, UserSecretProvider

import gooey_ui as st


def secrets_widget(user: AppUser):
    return SecretsWidget(user=user).render()


class SecretsWidget:
    def __init__(
        self,
        *,
        user: AppUser,
        providers: list[UserSecretProvider] | None = None,
        base_key: str = "__user_secrets",
        state: dict | None = None,
    ):
        self.user = user
        self.providers = providers
        self.base_key = base_key
        self.state = state or st.session_state

    def get_state_keys_by_provider(self, provider: UserSecretProvider):
        return {
            "value": f"{self.base_key}_{provider.value}_value",
            "preview": f"{self.base_key}_{provider.value}_preview",
            # TODO: more later - name, description, provider select?, ...
        }

    def fetch_secrets(self) -> dict[UserSecretProvider, list[UserSecret]]:
        if self.providers is None:
            secrets = self.user.secrets.all()
        else:
            secrets = self.user.secrets.filter(provider__in=self.providers)

        grouped: dict[UserSecretProvider, list[UserSecret]] = {}
        for secret in secrets:
            grouped.setdefault(secret.provider, []).append(secret)

        return grouped

    def render(self):
        st.write(
            dedent(
                """\
                Securely store 3rd party API keys here and we'll call
                them whenever you use their functionality in a workflow.
            """
            )
        )

        # TODO: change UX to allow adding multiple keys for single key provider
        secrets_by_provider = self.fetch_secrets()

        self._header_row()
        for provider in UserSecretProvider:
            secrets = secrets_by_provider.get(provider)
            provider_secret = secrets[0] if secrets else None

            provider_col, value_col, action_col = st.columns([1, 3, 1])

            with provider_col:
                align_items_center(provider_col)
                st.write(f"**{provider.label}**")

            with action_col:
                align_items_center(action_col)
                edit_mode_actions, view_mode_actions = st.div(), st.div()
                with edit_mode_actions:
                    save_button = st.button("🔑 Save")
                    cancel_edit_button = st.button("❌ Cancel")
                with view_mode_actions:
                    edit_button = st.button("✏️ Edit", type="secondary")
                    delete_button = st.button("🗑️ Delete")

            if delete_button:
                provider_secret = self._handle_delete(provider_secret)
            elif save_button:
                provider_secret = (
                    self._handle_update(provider_secret)
                    if provider_secret
                    else self._handle_add(provider)
                )
            elif cancel_edit_button:
                self._handle_cancel_edit(provider)

            is_editing = (self._is_editing(provider) or edit_button) and not save_button
            if is_editing:
                view_mode_actions.empty()
            elif provider_secret:
                edit_mode_actions.empty()
            else:
                # provider_secret is not there, user hasn't started typing yet
                view_mode_actions.empty()
                edit_mode_actions.empty()
                with action_col:
                    st.caption("Enter a secret key to save it.")

            with value_col:
                state_keys = self.get_state_keys_by_provider(provider)
                if is_editing or not provider_secret:
                    st.text_input(
                        label="",
                        key=state_keys["value"],
                        placeholder="sk-1234567890abcdefg",
                    )
                else:
                    self.state[state_keys["preview"]] = provider_secret.preview
                    st.text_input(
                        label="",
                        key=state_keys["preview"],
                        disabled=True,
                    )

    def _header_row(self):
        provider_col, value_col, action_col = st.columns([1, 3, 1])
        make_column_title = lambda title: st.write(f"**{title}**")

        with provider_col:
            make_column_title("Provider")

        with value_col:
            make_column_title("Value")

        with action_col:
            make_column_title("Actions")

    def _handle_add(self, provider: UserSecretProvider):
        state_keys = self.get_state_keys_by_provider(provider)

        secret = UserSecret.objects.create_secret(
            user=self.user,
            provider=provider,
            name=UserSecret.get_default_name_from_provider(provider),
            value=self.state.pop(state_keys["value"], ""),
        )
        st.success("Added!")
        return secret

    def _handle_update(self, secret: UserSecret):
        state_keys = self.get_state_keys_by_provider(
            UserSecretProvider(secret.provider)
        )

        secret.update_value(self.state.pop(state_keys["value"], "")).save()
        st.success("Saved!")

        return secret

    def _handle_delete(self, secret: UserSecret):
        assert secret is not None
        secret.delete_secret()
        st.success("Deleted!")
        return None

    def _handle_cancel_edit(self, provider: UserSecretProvider):
        self.state.pop(self.get_state_keys_by_provider(provider)["value"])

    def _is_editing(self, provider: UserSecretProvider) -> bool:
        state_keys = self.get_state_keys_by_provider(provider)

        return bool(self.state.get(state_keys["value"]))


def align_items_center(component):
    component.node.props["className"] = (
        component.node.props.get("className", "") + " d-flex align-items-center"
    )
