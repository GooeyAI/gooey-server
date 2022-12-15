const firebaseConfig = {
    apiKey: "AIzaSyC7j8WI-P_BZQogR809B2QbaH_aP1KsVeM",
    authDomain: "dara-c1b52.firebaseapp.com",
    databaseURL: "https://dara-c1b52.firebaseio.com",
    projectId: "dara-c1b52",
    storageBucket: "dara-c1b52.appspot.com",
    messagingSenderId: "6678571001",
    appId: "1:6678571001:web:885c6e8140b3f9eb713f28",
    measurementId: "G-09W5N835PE"
};

// Initialize Firebase
const app = firebase.initializeApp(firebaseConfig);

firebase.auth().signInAnonymously();

function onSignIn(user) {
    if (!user) return;

    // As httpOnly cookies are to be used, do not persist any state client side.
    firebase.auth().setPersistence(firebase.auth.Auth.Persistence.NONE);

    // Get the user's ID token as it is needed to exchange for a session cookie.
    user.getIdToken().then(idToken => {
            // Session login endpoint is queried and the session cookie is set.
            const xhr = new XMLHttpRequest();
            xhr.open("POST", '/sessionLogin', true);

            // Send the proper header information along with the request
            xhr.setRequestHeader("Content-Type", "application/json");

            xhr.onreadystatechange = () => { // Call a function when the state changes.
                if (xhr.readyState === XMLHttpRequest.DONE && xhr.status === 200) {
                    // Request finished. Do processing here.
                    const nextUrl = new URLSearchParams(window.location.search).get("next") || window.location;
                    window.location = nextUrl;
                }
            }
            xhr.send(idToken);
        }
    );
}

function handleCredentialResponse(response) {
    // Build Firebase credential with the Google ID token.
    const idToken = response.credential;
    const credential = firebase.auth.GoogleAuthProvider.credential(idToken);

    // Sign in with credential from the Google user.
    firebase.auth().currentUser.linkWithCredential(credential).then(authResult => {
        onSignIn(authResult.user);
    }, _ => {
        firebase.auth().signInWithCredential(credential).then(authResult => {
            onSignIn(authResult.user);
        });
    });
}
