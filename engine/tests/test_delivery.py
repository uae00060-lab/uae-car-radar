import os
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import notify
import radar

class Delivery(unittest.TestCase):
    def test_successful_channel_is_not_resent(self):
        with patch.dict(os.environ, {"SMTP_USER":"a", "SMTP_PASSWORD":"b", "TELEGRAM_BOT_TOKEN":"c", "TELEGRAM_CHAT_ID":"d"}, clear=True):
            self.assertEqual(notify.retry_channels({"telegram":notify.SENT,"email":"فشل"}), ["email"])

    def test_selected_channel_only(self):
        with patch.object(notify,"telegram") as tg, patch.object(notify,"email",return_value=notify.SENT) as mail:
            self.assertEqual(notify.send_all("subject","text","short",channels=["email"]), {"email":notify.SENT})
            tg.assert_not_called()
            mail.assert_called_once()

    def test_pending_delivery_survives_failure_then_clears(self):
        eng={"runs":[{"id":"r","notify":{"telegram":notify.SENT}}],"delivery_queue":{
            "r":{"subject":"subject","text":"text","short":"short","result":{"telegram":notify.SENT,"email":"فشل"}}}}
        with patch.dict(os.environ, {"SMTP_USER":"a","SMTP_PASSWORD":"b","TELEGRAM_BOT_TOKEN":"c","TELEGRAM_CHAT_ID":"d"}, clear=True), patch.object(radar,"finish"), patch.object(notify,"send_all",side_effect=[{"email":"فشل"},{"email":notify.SENT}]) as send:
            radar.retry_deliveries(eng,"key")
            self.assertIn("r",eng["delivery_queue"])
            radar.retry_deliveries(eng,"key")
            self.assertNotIn("r",eng["delivery_queue"])
            self.assertEqual(eng["runs"][0]["notify"]["telegram"], notify.SENT)
            self.assertEqual(send.call_args.kwargs["channels"],["email"])
