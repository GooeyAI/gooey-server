import datetime

import pandas as pd
import streamlit as st
from django.db.models import Count

from Home import check_password
from bots.models import (
    BotIntegration,
    Message,
    CHATML_ROLE_USER,
    Feedback,
)

st.set_page_config(layout="wide")
if not check_password():
    st.stop()


@st.cache_data
def convert_df(df):
    return df.to_csv(index=True).encode("utf-8")


START_DATE = datetime.datetime(2023, 5, 1).date()  # 1st May 20223
DEFAULT_BOT_ID = 8  # Telugu bot id is 8


def main():
    st.markdown(
        """
        # Gooey.AI Bot Stats
        """
    )
    bots = BotIntegration.objects.all()
    default_bot_index = 0
    for index, bot in enumerate(bots):
        if bot.id == DEFAULT_BOT_ID:
            default_bot_index = index

    col1, col2 = st.columns([25, 75])
    with col1:
        bot = st.selectbox(
            "Select Bot",
            index=default_bot_index,
            options=[b for b in bots],
            # format_func=lambda b: f"{b}",
        )
        view = st.radio("View", ["Daily", "Weekly"], index=0)
        start_date = st.date_input("Start date", START_DATE)
    if bot and start_date:
        with st.spinner("Loading stats..."):
            date = start_date
            data = []
            convo_by_msg_exchanged = (
                Message.objects.filter(
                    created_at__date__gte=start_date,
                    created_at__date__lte=datetime.date.today(),
                )
                .values_list(
                    "conversation__bot_integration__name",
                    "conversation__wa_phone_number",
                )
                .annotate(messages_exchanged=Count("conversation"))
            )
            top_5_conv_by_message = pd.DataFrame(
                convo_by_msg_exchanged.order_by("-messages_exchanged")[:5],
                columns=["Bot Name", "Phone Number", "Messages Exchanged"],
            )
            bottom_5_conv_by_message = pd.DataFrame(
                convo_by_msg_exchanged.order_by("messages_exchanged")[:5],
                columns=["Bot Name", "Phone Number", "Messages Exchanged"],
            )

            if view == "Weekly":
                delta = datetime.timedelta(days=7)
            if view == "Daily":
                delta = datetime.timedelta(days=1)
            while date <= datetime.date.today():
                messages_received = Message.objects.filter(
                    created_at__date__gte=date,
                    created_at__date__lt=date + delta,
                ).filter(conversation__bot_integration=bot, role=CHATML_ROLE_USER)

                unique_senders = (
                    messages_received.values_list("conversation__id", flat=True)
                    .distinct()
                    .order_by()
                ).count()

                positive_feedbacks = Feedback.objects.filter(
                    message__conversation__bot_integration=bot,
                    rating=Feedback.Rating.RATING_THUMBS_UP,
                    created_at__date__gte=date,
                    created_at__date__lt=date + delta,
                ).count()

                negative_feedbacks = Feedback.objects.filter(
                    message__conversation__bot_integration=bot,
                    rating=Feedback.Rating.RATING_THUMBS_DOWN,
                    created_at__date__gte=date,
                    created_at__date__lt=date + delta,
                ).count()

                unique_feedback_givers = (
                    Feedback.objects.filter(
                        message__conversation__bot_integration=bot,
                        created_at__date__gte=date,
                        created_at__date__lt=date + delta,
                    )
                    .distinct()
                    .count()
                )
                try:
                    messages_per_unique_sender = round(
                        len(messages_received) / unique_senders
                    )

                except ZeroDivisionError:
                    messages_per_unique_sender = 0

                ctx = {
                    "date": date,
                    "messages_received": len(messages_received),
                    "negative_feedbacks": negative_feedbacks,
                    "positive_feedbacks": positive_feedbacks,
                    "unique_senders": unique_senders,
                    "unique_feedback_givers": unique_feedback_givers,
                    "messages_per_unique_sender": messages_per_unique_sender,
                }
                data.append(ctx)
                date += delta

        df = pd.DataFrame(data)

        csv = convert_df(df)
        st.write("### Stats")
        st.download_button(
            "Download as csv", csv, "file.csv", "text/csv", key="download-csv"
        )
        with col2:
            st.line_chart(
                df,
                x="date",
                y=[
                    "messages_received",
                ],
            )
            st.line_chart(
                df,
                x="date",
                y=[
                    "unique_senders",
                    "unique_feedback_givers",
                    "positive_feedbacks",
                    "negative_feedbacks",
                    "messages_per_unique_sender",
                ],
            )

        st.dataframe(df, use_container_width=True)
        col1, col2 = st.columns(2)
        with col1:
            st.write("### Top 5 users")
            st.caption(f"{start_date} - {datetime.date.today()}")
            st.dataframe(top_5_conv_by_message)
        with col2:
            st.write("### Bottom 5 users")
            st.caption(f"{start_date} - {datetime.date.today()}")
            st.dataframe(bottom_5_conv_by_message)


main()
