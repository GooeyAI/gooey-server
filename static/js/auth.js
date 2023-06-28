const CLIENT_ID =
  "6678571001-hirtjjutehsmoi1jl0c0290kobdk8t8r.apps.googleusercontent.com";

const firebaseConfig = {
  apiKey: "AIzaSyC7j8WI-P_BZQogR809B2QbaH_aP1KsVeM",
  authDomain: "dara-c1b52.firebaseapp.com",
  databaseURL: "https://dara-c1b52.firebaseio.com",
  projectId: "dara-c1b52",
  storageBucket: "dara-c1b52.appspot.com",
  messagingSenderId: "6678571001",
  appId: "1:6678571001:web:885c6e8140b3f9eb713f28",
  measurementId: "G-09W5N835PE",
};

window.addEventListener("DOMContentLoaded", async function () {
  // Initialize Firebase
  const app = firebase.initializeApp(firebaseConfig);

  // As httpOnly cookies are to be used, do not persist any state client side.
  firebase.auth().setPersistence(firebase.auth.Auth.Persistence.NONE);
});

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
    "[data-replace-login-spinner]"
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
