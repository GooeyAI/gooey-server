initFirebaseUi("#firebaseui-auth-container", [
  // Leave the lines as is for the providers you want to offer your users.
  {
    // Use the classic Firebase Google popup (not GIS / One Tap). Passing
    // clientId here makes FirebaseUI initialize GSI a second time, which
    // after logout sends a malformed request to accounts.google.com on iOS.
    provider: firebase.auth.GoogleAuthProvider.PROVIDER_ID,
    customParameters: {
      prompt: "select_account",
    },
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
