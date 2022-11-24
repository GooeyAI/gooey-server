const firebaseConfig = {
    apiKey: 'AIzaSyDZuvLUXo6wzSMGiAOdFWNVXBjVh2MKPYE',
    appId: '1:6678571001:web:a03359c10efaa1cd713f28',
    messagingSenderId: '6678571001',
    projectId: 'dara-c1b52',
    authDomain: 'dara-c1b52.firebaseapp.com',
    databaseURL: 'https://dara-c1b52.firebaseio.com',
    storageBucket: 'dara-c1b52.appspot.com',
    measurementId: 'G-KGQDVPK6PV',
};

window.addEventListener('load', function () {
    // Initialize Firebase
    const app = firebase.initializeApp(firebaseConfig);

    // Initialize Analytics
    const analytics = firebase.analytics(app);
    analytics.logEvent('init');

    // As httpOnly cookies are to be used, do not persist any state client side.
    firebase.auth().setPersistence(firebase.auth.Auth.Persistence.NONE);
});


function onSignIn(user) {
    if (!user) return;

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
                const next = new URLSearchParams(window.location.search).get("next") || window.location;
                window.location = next;
            }
        }
        xhr.send(idToken);
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
