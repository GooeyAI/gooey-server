from gooeysite import wsgi

assert wsgi

import datetime

import pandas as pd
import streamlit as gui
from django.db.models import Count

from bots.models import (
    BotIntegration,
    Message,
    CHATML_ROLE_USER,
    Feedback,
    Conversation,
)

gui.set_page_config(layout="wide")


@gui.cache_data
def convert_df(df):
    return df.to_csv(index=True).encode("utf-8")


START_DATE = datetime.datetime(2023, 5, 1).date()  # 1st May 20223
DEFAULT_BOT_ID = 8  # Telugu bot id is 8


def main():
    gui.markdown(
        """
        # Gooey.AI Bot Stats
        """
    )
    bots = BotIntegration.objects.all()
    default_bot_index = 0
    for index, bot in enumerate(bots):
        if bot.id == DEFAULT_BOT_ID:
            default_bot_index = index

    col1, col2 = gui.columns([25, 75])
    with col1:
        bot = gui.selectbox(
            "Select Bot",
            index=default_bot_index,
            options=[b for b in bots],
            # format_func=lambda b: f"{b}",
        )
        view = gui.radio("View", ["Daily", "Weekly"], index=0)
        start_date = gui.date_input("Start date", START_DATE)
    if bot and start_date:
        with gui.spinner("Loading stats..."):
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
                    Conversation.objects.filter(
                        bot_integration=bot,
                        messages__feedbacks__isnull=False,
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
                    "Messages_Sent": len(messages_received),
                    "Neg_feedback": negative_feedbacks,
                    "Pos_feedback": positive_feedbacks,
                    "Senders": unique_senders,
                    "Unique_feedback_givers": unique_feedback_givers,
                    "Msgs_per_sender": messages_per_unique_sender,
                }
                data.append(ctx)
                date += delta

        df = pd.DataFrame(data)

        csv = convert_df(df)
        gui.write("### Stats")
        gui.download_button(
            "Download as csv", csv, "file.csv", "text/csv", key="download-csv"
        )
        with col2:
            gui.line_chart(
                df,
                x="date",
                y=[
                    "Messages_Sent",
                ],
            )
            gui.line_chart(
                df,
                x="date",
                y=[
                    "Senders",
                    "Unique_feedback_givers",
                    "Pos_feedback",
                    "Neg_feedback",
                    "Msgs_per_sender",
                ],
            )

        gui.dataframe(df, use_container_width=True)
        col1, col2 = gui.columns(2)
        with col1:
            gui.write("### Top 5 users")
            gui.caption(f"{start_date} - {datetime.date.today()}")
            gui.dataframe(top_5_conv_by_message)
        with col2:
            gui.write("### Bottom 5 users")
            gui.caption(f"{start_date} - {datetime.date.today()}")
            gui.dataframe(bottom_5_conv_by_message)


main()
