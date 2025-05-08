from daras_ai_v2.language_model import LargeLanguageModels


def test_deprecated_model_redirects():
    for model in LargeLanguageModels:
        if not model.is_deprecated:
            continue
        # 1) There is a redirect_to on all deprecated models
        assert model.redirect_to, f"{model.name} is deprecated but has no redirect_to"

        # 2) The redirect_to points to a valid model
        assert model.redirect_to in LargeLanguageModels.__members__, (
            f"{model.name} redirects to invalid model {model.redirect_to}"
        )

        redirected_model = LargeLanguageModels[model.redirect_to]
        # 3) The redirected model is not deprecated
        assert not redirected_model.is_deprecated, (
            f"{model.name} redirects to deprecated model {model.redirect_to}"
        )
