import tempfile
import unittest
from unittest.mock import patch

import messaging


def session(username: str, role: str, display: str) -> dict:
    return {
        "authenticated": True,
        "user": {
            "uuid": f"{username}-uuid",
            "username": username,
            "display": display,
            "roles": [{"name": role}],
            "privileges": [],
            "userProperties": {},
        },
    }


class MessagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp.close()
        messaging.MESSAGING_DB_PATH = self.temp.name

    def tearDown(self) -> None:
        messaging.reset_for_tests(self.temp.name)

    def test_department_message_has_per_user_unread_state_and_attention_acknowledger(self) -> None:
        users = {
            "reception": session("reception", "Abikan:Reception", "Reception"),
            "pharmacy-a": session("pharmacy-a", "Abikan:Pharmacy", "Pharmacist A"),
            "pharmacy-b": session("pharmacy-b", "Abikan:Pharmacy", "Pharmacist B"),
            "outsider": session("outsider", "Abikan:Laboratory", "Laboratory"),
        }

        def require_session(cookie: str) -> dict:
            return users[cookie]

        with patch.object(messaging.core, "require_session", side_effect=require_session), patch.object(
            messaging.notifications, "emit"
        ) as emit:
            created = messaging.create_conversation(
                {"type": "department", "workplace": "pharmacy"},
                "reception",
            )
            conversation_id = created["conversation"]["id"]
            messaging.send_message(conversation_id, {"body": "Patient is waiting."}, "reception")

            pharmacy_a = messaging.get_conversation(conversation_id, "pharmacy-a")["conversation"]
            pharmacy_b = messaging.get_conversation(conversation_id, "pharmacy-b")["conversation"]
            self.assertEqual(pharmacy_a["unreadCount"], 1)
            self.assertEqual(pharmacy_b["unreadCount"], 1)

            message_id = pharmacy_a["messages"][-1]["id"]
            messaging.mark_read(conversation_id, {"messageId": message_id}, "pharmacy-a")
            pharmacy_a_after = messaging.get_conversation(conversation_id, "pharmacy-a")["conversation"]
            pharmacy_b_after = messaging.get_conversation(conversation_id, "pharmacy-b")["conversation"]
            self.assertEqual(pharmacy_a_after["unreadCount"], 0)
            self.assertEqual(pharmacy_b_after["unreadCount"], 1)

            attention = messaging.request_attention(conversation_id, {}, "reception")["attention"]
            self.assertEqual(attention["status"], "requested")
            acknowledged = messaging.acknowledge_attention(attention["id"], "pharmacy-a")["attention"]
            self.assertEqual(acknowledged["acknowledgedByUsername"], "pharmacy-a")
            self.assertEqual(acknowledged["status"], "acknowledged")
            self.assertTrue(
                any(call.kwargs.get("event_type") == "department_attention_requested" for call in emit.call_args_list)
            )

            with self.assertRaises(messaging.core.ApiError) as error:
                messaging.get_conversation(conversation_id, "outsider")
            self.assertEqual(error.exception.status, 403)

    def test_direct_conversation_validates_target_and_authorizes_only_users(self) -> None:
        users = {
            "doctor": session("doctor", "Abikan:Doctor", "Doctor"),
            "pharmacist": session("pharmacist", "Abikan:Pharmacy", "Pharmacist"),
            "nurse": session("nurse", "Abikan:Nursing", "Nurse"),
        }

        def require_session(cookie: str) -> dict:
            return users[cookie]

        def openmrs_get(path: str, cookie: str) -> dict:
            if "/user?" in path:
                return {"results": [{"username": "pharmacist", "retired": False}]}
            return {}

        with patch.object(messaging.core, "require_session", side_effect=require_session), patch.object(
            messaging.core, "openmrs_get", side_effect=openmrs_get
        ):
            created = messaging.create_conversation(
                {"type": "direct", "username": "pharmacist"},
                "doctor",
            )
            conversation_id = created["conversation"]["id"]
            messaging.send_message(conversation_id, {"body": "Please review."}, "doctor")
            self.assertEqual(
                messaging.get_conversation(conversation_id, "pharmacist")["conversation"]["messages"][-1]["body"],
                "Please review.",
            )
            with self.assertRaises(messaging.core.ApiError) as error:
                messaging.get_conversation(conversation_id, "nurse")
            self.assertEqual(error.exception.status, 403)

            with patch.object(messaging.notifications, "emit"):
                attention = messaging.request_attention(conversation_id, {}, "doctor")["attention"]
            self.assertEqual(attention["recipientUsername"], "pharmacist")


    def test_pharmacy_and_nursing_can_call_and_text_each_other(self) -> None:
        users = {
            "pharmacy": session("pharmacy", "Abikan:Pharmacy", "Pharmacy"),
            "nurse": session("nurse", "Abikan:Nursing", "Nurse"),
            "pharmacist-two": session("pharmacist-two", "Abikan:Pharmacy", "Pharmacy Two"),
        }

        def require_session(cookie: str) -> dict:
            return users[cookie]

        with patch.object(messaging.core, "require_session", side_effect=require_session), patch.object(
            messaging.notifications, "emit"
        ) as emit:
            created = messaging.create_conversation(
                {"type": "department", "workplace": "nursing"},
                "pharmacy",
            )
            conversation_id = created["conversation"]["id"]
            pharmacy_view = messaging.get_conversation(conversation_id, "pharmacy")["conversation"]
            nurse_view = messaging.get_conversation(conversation_id, "nurse")["conversation"]
            self.assertEqual(pharmacy_view["label"], "Nursing")
            self.assertEqual(nurse_view["label"], "Pharmacy")

            attention = messaging.request_attention(conversation_id, {}, "pharmacy")["attention"]
            self.assertEqual(attention["recipientWorkplace"], "nursing")
            self.assertTrue(
                any(
                    call.kwargs.get("event_type") == "department_attention_requested"
                    and call.kwargs.get("recipient_workplace") == "nursing"
                    for call in emit.call_args_list
                )
            )

            messaging.send_message(conversation_id, {"body": "Please come to Pharmacy."}, "pharmacy")
            self.assertEqual(
                messaging.get_conversation(conversation_id, "nurse")["conversation"]["unreadCount"],
                1,
            )
            messaging.send_message(conversation_id, {"body": "On our way."}, "nurse")
            self.assertEqual(
                messaging.get_conversation(conversation_id, "pharmacy")["conversation"]["unreadCount"],
                1,
            )
            other_pharmacist = messaging.get_conversation(conversation_id, "pharmacist-two")["conversation"]
            self.assertEqual(other_pharmacist["label"], "Nursing")

            emit.reset_mock()
            reverse = messaging.request_attention(conversation_id, {}, "nurse")["attention"]
            self.assertEqual(reverse["recipientWorkplace"], "pharmacy")
            self.assertTrue(
                any(
                    call.kwargs.get("recipient_workplace") == "pharmacy"
                    for call in emit.call_args_list
                )
            )


if __name__ == "__main__":
    unittest.main()
