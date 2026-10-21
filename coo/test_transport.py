import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from transport import retry_delay, teams_get


class RetryTests(unittest.TestCase):
    def test_retry_after_seconds_and_http_date(self):
        self.assertEqual(retry_delay('12'), 12)
        self.assertEqual(retry_delay('Wed, 21 Oct 2026 09:30:10 GMT', datetime(2026,10,21,9,30,tzinfo=timezone.utc)), 10)

    def test_five_retries_then_stop(self):
        session, response, sleep = Mock(), Mock(status_code=429, headers={'Retry-After': '9'}), Mock()
        session.get.return_value = response
        with self.assertRaises(RuntimeError):
            teams_get(session, 'https://graph.microsoft.com/target', sleep)
        self.assertEqual(session.get.call_count, 6)
        self.assertEqual(sleep.call_count, 5)
        sleep.assert_called_with(9)

    def test_success_after_rate_limit(self):
        session, sleep = Mock(), Mock()
        ok = Mock(status_code=200)
        ok.json.return_value = {'value': []}
        session.get.side_effect = [Mock(status_code=429, headers={'Retry-After': '3'}), ok]
        self.assertEqual(teams_get(session, 'https://graph.microsoft.com/target', sleep), {'value': []})
        sleep.assert_called_once_with(3)

    def test_invalid_retry_header_stops(self):
        with self.assertRaises(RuntimeError):
            retry_delay(None)


if __name__ == '__main__':
    unittest.main()
