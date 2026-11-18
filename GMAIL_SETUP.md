# Gmail account check-in

The check-in identity comes from the GLaDOS session, not a hardcoded email in the old Python script.

- `COOKIES` (Actions Secret): the current account's `gld:sess` and `gld:sess.sig` pair. Do not add the old account's `koa:` cookies or the account-switching `gld:accts` cookie.
- `GLADOS_EXPECTED_EMAIL` (Actions repository Variable): the intended account email. The browser checks `/api/user/status` and stops before check-in if the identity differs or authentication fails.
- No Gmail password, IMAP access, or authentication email access is needed. When the session expires, log in to GLaDOS and replace the Cookie Secret.

`browser_checkin.py` opens the official page in standard Chromium and clicks its Checkin button. The website generates its own request. The script does not click CAPTCHA checkboxes, solve image challenges, forge verification tokens, or replay a request whose outcome is unknown. Interactive verification or an unexpected response fails the run.

Only API business responses `code=0` (new check-in) and `code=1` (already recorded) count as success. Known verification-error messages still fail even if paired with those codes. Points exchange is not performed by the browser runner.

The original daily schedule remains UTC 04:00 (12:00 Asia/Shanghai), subject to GitHub Actions scheduling delays. Monthly keepalive is unchanged. Local response/account tests: `python -m unittest discover -s tests -v`.
