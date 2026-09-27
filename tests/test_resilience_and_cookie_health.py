"""
Unit Tests for Phase 5: Reliability & Monitoring
- Circuit Breaker (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Exponential Backoff Retry Decorator
- Cookie Health Checker (Shopee & Facebook)
- Cookie Health & Resilience API Endpoints
"""

import unittest
from unittest.mock import patch, MagicMock

from modules.common.resilience import (
    CircuitBreaker, CircuitState, CircuitBreakerOpenException,
    retry_with_backoff, get_all_resilience_status
)
from modules.monitoring.cookie_health import CookieHealthChecker
from api.settings_router import get_cookie_health, get_resilience_status


class TestResilienceAndCookieHealth(unittest.TestCase):

    def test_01_circuit_breaker_trips_to_open(self):
        """Kiểm tra Circuit Breaker chuyển sang OPEN sau khi gặp đủ số lần lỗi liên tiếp"""
        cb = CircuitBreaker("TestService", failure_threshold=3, recovery_timeout=2.0)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())

        # Thử 2 lần lỗi -> vẫn CLOSED
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.failure_count, 2)

        # Lần lỗi thứ 3 -> Tripped to OPEN
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

        # Gọi khi đang OPEN phải ném CircuitBreakerOpenException
        with self.assertRaises(CircuitBreakerOpenException):
            cb.call(lambda: "should_not_run")

        print("[PASS] test_01_circuit_breaker_trips_to_open passed")

    def test_02_circuit_breaker_half_open_and_recovery(self):
        """Kiểm tra Circuit Breaker chuyển từ OPEN sang HALF_OPEN rồi phục hồi về CLOSED khi request thành công"""
        cb = CircuitBreaker("TestRecovery", failure_threshold=2, recovery_timeout=0.2)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        # Giả lập thời gian trôi qua recovery_timeout
        import time
        time.sleep(0.25)

        # Lúc này can_execute phải chuyển sang HALF_OPEN
        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # Thành công -> chuyển về CLOSED
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.failure_count, 0)

        print("[PASS] test_02_circuit_breaker_half_open_and_recovery passed")

    def test_03_retry_with_backoff_success_on_retry(self):
        """Kiểm tra decorator retry_with_backoff tự động thử lại và thành công ở lần 2"""
        attempts = 0

        @retry_with_backoff(retries=3, initial_delay=0.01, backoff_factor=1.5, exceptions=(ValueError,))
        def flaky_function():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ValueError("Tạm thời mất kết nối")
            return "SUCCESS_DATA"

        result = flaky_function()
        self.assertEqual(result, "SUCCESS_DATA")
        self.assertEqual(attempts, 2)
        print("[PASS] test_03_retry_with_backoff_success_on_retry passed")

    def test_04_cookie_health_checker_structure(self):
        """Kiểm tra cấu trúc báo cáo của CookieHealthChecker khi không có cookie hoặc cookie giả lập"""
        checker = CookieHealthChecker()
        
        # Test khi không có cookie (truyền rỗng "")
        shopee_res = checker.check_shopee_cookie(cookie="")
        self.assertIn("status", shopee_res)
        self.assertEqual(shopee_res["status"], "MISSING")
        self.assertFalse(shopee_res["valid"])

        fb_res = checker.check_facebook_cookie(cookie="")
        self.assertIn("status", fb_res)
        self.assertFalse(fb_res["valid"])

        # Test check_all (không alert)
        all_res = checker.check_all(alert_on_failure=False)
        self.assertIn("last_checked", all_res)
        self.assertIn("shopee", all_res)
        self.assertIn("facebook", all_res)
        self.assertIn("all_healthy", all_res)

        print("[PASS] test_04_cookie_health_checker_structure passed")

    def test_05_api_endpoints_cookie_and_resilience(self):
        """Kiểm tra API /api/settings/cookie-health và /api/settings/resilience-status qua direct functions"""
        # GET cookie-health
        data = get_cookie_health()
        self.assertIn("shopee", data)
        self.assertIn("facebook", data)

        # GET resilience-status
        res_data = get_resilience_status()
        self.assertIn("shopee", res_data)
        self.assertIn("lazada", res_data)
        self.assertIn("telegram", res_data)
        self.assertIn("tinyurl", res_data)
        self.assertEqual(res_data["shopee"]["state"], "CLOSED")

        print("[PASS] test_05_api_endpoints_cookie_and_resilience passed")


if __name__ == "__main__":
    unittest.main()
