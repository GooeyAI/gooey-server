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

window.addEventListener('load', function () {
    // Initialize Firebase
    const app = firebase.initializeApp(firebaseConfig);

    // As httpOnly cookies are to be used, do not persist any state client side.
    firebase.auth().setPersistence(firebase.auth.Auth.Persistence.NONE);
});


function onSignIn(user) {
    if (!user) return;
    // Get the user's ID token as it is needed to exchange for a session cookie.
    user.getIdToken().then(idToken => {
        const form = document.body.appendChild(document.createElement('form'));
        let input = form.appendChild(document.createElement('input'));
        form.method = "POST";
        input.type = "hidden";
        input.name = "idToken";
        input.value = idToken;
        form.submit();
    });
}

function handleCredentialResponse(response) {
    // Build Firebase credential with the Google ID token.
    const idToken = response.credential;
    const credential = firebase.auth.GoogleAuthProvider.credential(idToken);

    // Sign in with credential from the Google user.
    firebase.auth().signInWithCredential(credential).then(authResult => {
        onSignIn(authResult.user);
    });
}
