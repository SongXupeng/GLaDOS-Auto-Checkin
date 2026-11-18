import unittest
from unittest.mock import Mock
from browser_checkin import accepted_result, activate_verification_checkbox, already_recorded, session_cookies, verify_identity


class BrowserCheckinTests(unittest.TestCase):
    def test_only_named_cloudflare_checkbox_is_activated(self):
        page = Mock()
        page.frames = [Mock(url="https://challenges.cloudflare.com/widget")]
        client = page.context.new_cdp_session.return_value
        client.send.return_value = {"nodes": [{"role": {"value": "checkbox"},
            "name": {"value": "Verify you are human"}, "backendDOMNodeId": 42}]}
        self.assertTrue(activate_verification_checkbox(page))
        page.keyboard.press.assert_called_once_with("Space")
        client.send.assert_any_call("DOM.focus", {"backendNodeId": 42})
        client.detach.assert_called_once()

    def test_other_origins_and_disabled_controls_are_untouched(self):
        for host, disabled in (("challenges.cloudflare.com.evil.example", False),
                               ("challenges.cloudflare.com", True)):
            page = Mock()
            page.frames = [Mock(url="https://" + host + "/widget")]
            page.context.new_cdp_session.return_value.send.return_value = {"nodes": [
                {"role": {"value": "checkbox"}, "name": {"value": "Verify you are human"},
                 "backendDOMNodeId": 42, "properties": [{"name": "disabled", "value": {"value": disabled}}]}]}
            self.assertFalse(activate_verification_checkbox(page))
            page.keyboard.press.assert_not_called()

    def test_recorded_button_is_not_submitted_again(self):
        self.assertTrue(already_recorded("Checkin! Got 2 Points"))
        self.assertFalse(already_recorded("Checkin"))
        self.assertFalse(already_recorded("Checking in..."))

    def test_cookie_scope_excludes_old_accounts(self):
        cookies = session_cookies("koa:sess=old; gld:accts=accounts; gld:sess=new; gld:sess.sig=signature")
        self.assertEqual([c["name"] for c in cookies], ["gld:sess", "gld:sess.sig"])

    def test_missing_or_duplicate_cookie_is_rejected(self):
        for cookie in ("", "gld:sess=a", "gld:sess=a; gld:sess=b; gld:sess.sig=c"):
            with self.assertRaises(ValueError):
                session_cookies(cookie)

    def test_wrong_or_expired_identity_never_checks_in(self):
        for status in ({"code": 0, "data": {"email": "old@example.com"}}, {"code": -2}):
            with self.assertRaises(ValueError):
                verify_identity(status, "new@example.com")

    def test_correct_identity(self):
        data = {"email": "New@example.com", "leftDays": 571}
        self.assertEqual(verify_identity({"code": 0, "data": data}, "new@example.com"), data)

    def test_verification_errors_never_count_as_success(self):
        for result in ({"code": 5}, {"code": 4}, {"code": 1, "message": "Cloudflare verification failed"}):
            self.assertFalse(accepted_result(result))
        self.assertTrue(accepted_result({"code": 0, "message": "success"}))
        self.assertTrue(accepted_result({"code": 1, "message": "already checked in"}))


if __name__ == "__main__":
    unittest.main()
