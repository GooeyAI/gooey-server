(async () => {
  await window.waitUntilHydrated;
  // load anonymous user before initializing FirebaseUI
  await loadAnonymousUser();
  // Initialize the FirebaseUI Widget using Firebase.
  const ui = new firebaseui.auth.AuthUI(firebase.auth());

  const uiConfig = loadUiConfig();
  ui.start("#firebaseui-auth-sso-container", uiConfig);
})();

function loadUiConfig() {
  let signInOptions = JSON.parse(document.getElementById("firebaseui-auth-sso-container").dataset.ssoProviders);

  return {
    // Whether to upgrade anonymous users should be explicitly provided.
    // The user must already be signed in anonymously before FirebaseUI is
    // rendered.
    autoUpgradeAnonymousUsers: true,
    // Will use popup for IDP Providers sign-in flow instead of the default, redirect.
    signInFlow: "popup",
    // signInSuccessUrl: '/',
    callbacks: {
      signInSuccessWithAuthResult: function(authResult, redirectUrl) {
        console.log("signInSuccessWithAuthResult");
        // User successfully signed in.
        // Return type determines whether we continue the redirect automatically
        // or whether we leave that to developer to handle.
        handleAuthResult(authResult);
        return false;
      },
      // signInFailure callback must be provided to handle merge conflicts which
      // occur when an existing credential is linked to an anonymous user.
      signInFailure: function(error) {
        // For merge conflicts, the error.code will be
        // 'firebaseui/anonymous-upgrade-merge-conflict'.
        if (error.code != "firebaseui/anonymous-upgrade-merge-conflict") {
          return Promise.resolve();
        }
        // Finish sign-in
        return handleCredential(error.credential);
      },
      uiShown: function() {
        // The widget is rendered.
        // Hide the loader.
        document.getElementById("firebaseui-spinner").style.display = "none";
      },
    },
    signInOptions
  };
};
