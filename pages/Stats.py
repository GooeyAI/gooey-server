import datetime
import pandas as pd

import streamlit as st
from decouple import config

from bots.models import BotIntegration, Message, CHATML_ROLE_USER, Feedback
from pages.UsageDashboard import password_check

st.set_page_config(layout="wide")


@st.experimental_memo
def convert_df(df):
    return df.to_csv(index=True).encode("utf-8")


def main():
    if not password_check():
        st.stop()
    bots = BotIntegration.objects.all()
    bot = st.selectbox(
        "Select Bot",
        options=[b for b in bots],
        format_func=lambda b: f"{b}",
    )
    start_date = st.date_input("Start date", datetime.date.today())
    if bot and start_date:
        with st.spinner("Loading stats..."):
            delta = datetime.timedelta(days=1)
            data = []
            dates = []
            while start_date <= datetime.date.today():
                messages_received = Message.objects.filter(
                    created_at__date=start_date
                ).filter(conversation__bot_integration=bot, role=CHATML_ROLE_USER)
                unique_senders = (
                    messages_received.values_list("conversation__id", flat=True)
                    .distinct()
                    .order_by()
                ).count()
                positive_feedbacks = Feedback.objects.filter(
                    message__conversation__bot_integration=bot,
                    rating=Feedback.Rating.RATING_THUMBS_UP,
                    created_at__date=start_date,
                ).count()
                negative_feedbacks = Feedback.objects.filter(
                    message__conversation__bot_integration=bot,
                    rating=Feedback.Rating.RATING_THUMBS_DOWN,
                    created_at__date=start_date,
                ).count()
                unique_feedback_givers = (
                    Feedback.objects.filter(
                        message__conversation__bot_integration=bot,
                        created_at__date=start_date,
                    )
                    .distinct()
                    .count()
                )
                try:
                    messages_per_unique_sender = "{:.2f}".format(
                        len(messages_received) / unique_senders
                    )
                except ZeroDivisionError:
                    messages_per_unique_sender = 0
                ctx = {
                    "messages_received": len(messages_received),
                    "unique_senders": unique_senders,
                    "positive_feedbacks": positive_feedbacks,
                    "negative_feedbacks": negative_feedbacks,
                    "unique_feedback_givers": unique_feedback_givers,
                    "messages_per_unique_sender": messages_per_unique_sender,
                }
                data.append(ctx)
                dates.append(start_date)
                start_date += delta

        df = pd.DataFrame(
            data,
            index=dates,
        )

        csv = convert_df(df)
        st.download_button(
            "Download as csv", csv, "file.csv", "text/csv", key="download-csv"
        )
        st.write("### Stats")
        st.table(df)


main()
