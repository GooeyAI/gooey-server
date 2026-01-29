(async () => {
  await window.waitUntilHydrated;

  // Initialize Firebase
  const app = firebase.initializeApp(window.FIREBASE_CONFIG);

  // As httpOnly cookies are to be used, do not persist any state client side.
  firebase.auth().setPersistence(firebase.auth.Auth.Persistence.NONE);
})();

async function initFirebaseUi(containerSelector, signInOptions) {
  await window.waitUntilHydrated;
  // load anonymous user before initializing FirebaseUI
  await loadAnonymousUser();
  // Initialize the FirebaseUI Widget using Firebase.
  let uiConfig = {
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
        const spinner = document.getElementById("firebaseui-spinner");
        if (spinner) spinner.style.display = "none";
      },
    },
    signInOptions,
  };
  let ui = new firebaseui.auth.AuthUI(firebase.auth());
  ui.start(containerSelector, uiConfig);
}
async function handleCredentialResponse(response) {
  showLoginProgress();
  await loadAnonymousUser();

  // Build Firebase credential with the Google ID token.
  const idToken = response.credential;
  const credential = firebase.auth.GoogleAuthProvider.credential(idToken);

  await handleCredential(credential);
}

async function handleCredential(credential) {
  showLoginProgress();

  let authResult;
  try {
    // upgrade anonymous user to a permanent account
    authResult = await firebase
      .auth()
      .currentUser.linkWithCredential(credential);
  } catch (e) {
    // if the user is already linked an account, just sign in
    authResult = await firebase.auth().signInWithCredential(credential);
  }

  await handleAuthResult(authResult);
}

async function handleAuthResult({ user }) {
  if (!user) return;
  showLoginProgress();

  // Get the user's ID token as it is needed to exchange for a session cookie.
  const idToken = await user.getIdToken();
  let action = "/login/";

  const windowUrl = new URL(window.location.href);
  // redirect back to the page that sent the user here
  let next = windowUrl.searchParams.get("next");
  // if no next param, redirect to the current page (but not the login page)
  if (!next && windowUrl.pathname !== action) {
    if (document.querySelector("[data-submitafterlogin]")) {
      windowUrl.searchParams.set("submitafterlogin", "1");
    }
    next = windowUrl.pathname + windowUrl.search + windowUrl.hash;
  }
  if (next) {
    action += "?" + new URLSearchParams({ next }).toString();
  }

  const form = document.body.appendChild(document.createElement("form"));
  let input = form.appendChild(document.createElement("input"));
  form.method = "POST";
  form.action = action;
  input.type = "hidden";
  input.name = "idToken";
  input.value = idToken;

  form.submit();
}

function showLoginProgress() {
  for (const elem of document.querySelectorAll(
    "[data-replace-login-spinner]",
  )) {
    elem.innerHTML = "<h5>Logging you in...</h5>";
  }
}

async function loadAnonymousUser() {
  if (!window._anonymous_user_token) return null;
  const credential = await firebase
    .auth()
    .signInWithCustomToken(window._anonymous_user_token);
  // make sure the user is marked as anonymous
  Object.defineProperty(credential.user, "isAnonymous", { value: true });
  console.log("loaded anonymous user", firebase.auth().currentUser.isAnonymous);
  return credential.user;
}

