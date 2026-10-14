import unittest
import importlib
from unittest.mock import Mock, patch

import checkin


class CheckinTests(unittest.TestCase):
    def test_blocked_response_takes_precedence_over_repeat_keywords(self):
        for code, message in (
            (4, "Automated check-in detected. Please sign in again to continue."),
            ("4", "already checked"),
            (1, "Automated check-in detected. Please sign in again to continue."),
        ):
            with self.subTest(code=code, message=message):
                self.assertEqual(checkin.classify_checkin(code, message), "blocked")

    def test_normal_results(self):
        self.assertEqual(checkin.classify_checkin(0, "Checkin! Got 5 Points"), "ok")
        self.assertEqual(checkin.classify_checkin(1, "already checked in"), "repeat")
        self.assertEqual(checkin.classify_checkin(1, "Today's observation logged. Return tomorrow for more points."), "repeat")
        self.assertEqual(checkin.classify_checkin(-2, "没有权限"), "fail")

    def test_user_agent_can_follow_the_login_browser(self):
        try:
            with patch.dict(checkin.os.environ, {"GLADOS_USER_AGENT": "  login-browser-agent  "}):
                importlib.reload(checkin)
                self.assertEqual(checkin.HEADERS_BASE["user-agent"], "login-browser-agent")
            with patch.dict(checkin.os.environ, {"GLADOS_USER_AGENT": "  "}):
                importlib.reload(checkin)
                self.assertIn("Chrome/155.0.0.0", checkin.HEADERS_BASE["user-agent"])
        finally:
            importlib.reload(checkin)

    def test_request_preserves_the_cookie_and_json_payload(self):
        session = Mock()
        session.post.return_value.json.return_value = {"code": 0, "points": 5}
        headers = {"cookie": "test-only", "user-agent": "configured-agent"}
        checkin.checkin_request(session, headers)
        args, kwargs = session.post.call_args
        self.assertEqual(args, (checkin.CHECKIN_URL,))
        self.assertEqual(kwargs["json"], {"token": "glados.cloud"})
        self.assertEqual(kwargs["headers"]["cookie"], "test-only")
        self.assertNotIn("content-type", headers)

    def test_blocked_account_remains_failed_even_when_status_works(self):
        session = Mock()
        blocked = {"code": 4, "message": "Automated check-in detected. Please sign in again to continue."}
        with patch.object(checkin, "checkin_request", return_value=blocked) as request:
            with patch.object(checkin, "api_get", side_effect=[
                {"code": 0, "data": {"email": "test@example.com", "leftDays": 139}},
                {"code": 0, "points": 483},
            ]):
                result = checkin.checkin_account(session, "test-only", 1)
        self.assertEqual(result["result"], "blocked")
        self.assertEqual(result["total_points"], "483 积分")
        self.assertEqual(request.call_count, 1)

    def test_all_blocked_accounts_return_nonzero(self):
        with patch.dict(checkin.os.environ, {"COOKIES": "gld:sess=test; gld:sess.sig=test"}, clear=True):
            with patch.object(checkin, "checkin_account", return_value={
                "index": 1, "email": "unknown", "status": "blocked", "result": "blocked",
                "total_points": "483 积分", "remaining_days": "139 天", "exchange": "-",
            }):
                with patch.object(checkin, "push_all", return_value=(0, 0)):
                    self.assertEqual(checkin.main(), 1)


if __name__ == "__main__":
    unittest.main()
