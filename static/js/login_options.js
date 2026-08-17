initFirebaseUi("#firebaseui-auth-container", [
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
]);
