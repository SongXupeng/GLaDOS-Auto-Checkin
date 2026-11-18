import unittest
from browser_checkin import accepted_result, session_cookies, verify_identity


class BrowserCheckinTests(unittest.TestCase):
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
