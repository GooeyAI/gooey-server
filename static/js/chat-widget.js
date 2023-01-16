<!-- minified snippet to load TalkJS without delaying your page -->
(function (t, a, l, k, j, s) {
    s = a.createElement('script');
    s.async = 1;
    s.src = "https://cdn.talkjs.com/talk.js";
    a.head.appendChild(s)
    ;k = t.Promise;
    t.Talk = {
        v: 3, ready: {
            then: function (f) {
                if (k) return new k(function (r, e) {
                    l.push([f, r, e])
                });
                l
                    .push([f])
            }, catch: function () {
                return k && new k()
            }, c: l
        }
    };
})(window, document, []);

Talk.ready.then(function () {
    const user = new Talk.User({
        id: "user-1234568",
        name: "Visitor",
    });
    const session = new Talk.Session({
        appId: gooeyTalkJSConfig.appId,
        me: user,
        //signature: {{ signature }}#}
    });
    const bot = new Talk.User({
        id: 'bot-654321',
        name: 'Gooey.AI',
        photoUrl: 'https://gooey.ai/favicon.ico',
    });

    const conversation = session.getOrCreateConversation(
        Talk.oneOnOneId(user, bot)
    );
    conversation.setParticipant(user);
    conversation.setParticipant(bot);

    if (gooeyTalkJSConfig.display == "inbox") {
        const inbox = session.createInbox();
        inbox.select(conversation);
        inbox.mount(document.getElementById("gooey-chat-container"));
    } else if (gooeyTalkJSConfig.display == "popup") {
        const chatPopup = session.createPopup(conversation);
        console.log(chatPopup);
        chatPopup.mount({show: false});
        document.getElementsByClassName("__talkjs_popup")[0].style.height = "80vh";
    } else if (gooeyTalkJSConfig.display == "chatbox") {
        const chatbox = session.createChatbox();
        chatbox.select(conversation);
        chatbox.mount(document.getElementById('gooey-chat-container'));
    }
});
