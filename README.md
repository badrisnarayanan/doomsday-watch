# Doomsday seat watch (Chennai)
Checks District every 5 minutes for Avengers: Doomsday shows (Dec 17-20) at 9 Chennai cinemas and pushes an alert when seats open in centre, middle-to-back rows. It reads each show's seat map row by row: the front third of rows (never fewer than 3 rows from the screen), the side corners, couple seats and wheelchair seats are skipped. Tune with FRONT_ROWS, FRONT_FRACTION and SIDE_TRIM.

Setup: add repo secret `NTFY_TOPIC` (random string), install the ntfy app and subscribe to that topic. Optional email: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `MAIL_TO`.
Disable the workflow after the movie.
