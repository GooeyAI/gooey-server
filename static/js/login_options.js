window.addEventListener("DOMContentLoaded", async () => {
  // load anonymous user before initializing FirebaseUI
  await loadAnonymousUser();
  // Initialize the FirebaseUI Widget using Firebase.
  const ui = new firebaseui.auth.AuthUI(firebase.auth());
  ui.start("#firebaseui-auth-container", uiConfig);
});

const uiConfig = {
  // Whether to upgrade anonymous users should be explicitly provided.
  // The user must already be signed in anonymously before FirebaseUI is
  // rendered.
  autoUpgradeAnonymousUsers: true,
  // Will use popup for IDP Providers sign-in flow instead of the default, redirect.
  signInFlow: "popup",
  // signInSuccessUrl: '/',
  callbacks: {
    signInSuccessWithAuthResult: function (authResult, redirectUrl) {
      console.log("signInSuccessWithAuthResult");
      // User successfully signed in.
      // Return type determines whether we continue the redirect automatically
      // or whether we leave that to developer to handle.
      handleAuthResult(authResult);
      return false;
    },
    // signInFailure callback must be provided to handle merge conflicts which
    // occur when an existing credential is linked to an anonymous user.
    signInFailure: function (error) {
      // For merge conflicts, the error.code will be
      // 'firebaseui/anonymous-upgrade-merge-conflict'.
      if (error.code != "firebaseui/anonymous-upgrade-merge-conflict") {
        return Promise.resolve();
      }
      // The credential the user tried to sign in with.
      const cred = error.credential;
      // Finish sign-in
      return handleCredential(error.credential);
    },
    uiShown: function () {
      // The widget is rendered.
      // Hide the loader.
      document.getElementById("firebaseui-spinner").style.display = "none";
    },
  },
  signInOptions: [
    // Leave the lines as is for the providers you want to offer your users.
    {
      // Google provider must be enabled in Firebase Console to support one-tap
      // sign-up.
      provider: firebase.auth.GoogleAuthProvider.PROVIDER_ID,
      // Required to enable ID token credentials for this provider.
      // This can be obtained from the Credentials page of the Google APIs
      // console. Use the same OAuth client ID used for the Google provider
      // configured with GCIP or Firebase Auth.
      clientId: window.GOOGLE_CLIENT_ID,
    },
    {
      provider: "apple.com",
    },
    // firebase.auth.FacebookAuthProvider.PROVIDER_ID,
    // firebase.auth.TwitterAuthProvider.PROVIDER_ID,
    firebase.auth.GithubAuthProvider.PROVIDER_ID,
    firebase.auth.PhoneAuthProvider.PROVIDER_ID,
    // 'microsoft.com',
    {
      provider: firebase.auth.EmailAuthProvider.PROVIDER_ID,
      signInMethod: firebase.auth.EmailAuthProvider.EMAIL_LINK_SIGN_IN_METHOD,
    },
  ],
  // Required to enable one-tap sign-up credential helper.
  // credentialHelper: firebaseui.auth.CredentialHelper.GOOGLE_YOLO,
};
