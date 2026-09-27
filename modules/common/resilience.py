"""
Module Resilience: Circuit Breaker & Exponential Backoff Retry.
Bảo vệ hệ thống trước tình trạng API bên thứ ba bị sập, timeout, rate limit hoặc chặn WAF.
"""

import time
import logging
import functools
import threading
from enum import Enum
from typing import Callable, Any, Optional, Tuple, Dict, List

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"        # Hoạt động bình thường, mọi request được phép đi qua
    OPEN = "OPEN"            # Ngắt mạch, chặn toàn bộ request tránh làm quá tải API
    HALF_OPEN = "HALF_OPEN"  # Thử nghiệm 1 request sau thời gian cooldown để kiểm tra phục hồi


class CircuitBreakerOpenException(Exception):
    """Ngoại lệ ném ra khi mạch đang ở trạng thái OPEN (bị ngắt bảo vệ)"""
    def __init__(self, circuit_name: str, retry_after: float):
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit Breaker [{circuit_name}] đang ngắt (OPEN) để bảo vệ hệ thống. "
            f"Thử lại sau {retry_after:.1f} giây."
        )


class CircuitBreaker:
    """
    Bộ ngắt mạch bảo vệ (Circuit Breaker Pattern):
    - Đếm số lỗi liên tiếp.
    - Nếu vượt quá `failure_threshold` (mặc định 5), mạch chuyển sang OPEN.
    - Trong thời gian `recovery_timeout` (mặc định 180s), mọi request bị từ chối ngay lập tức.
    - Hết cooldown, chuyển sang HALF_OPEN để thăm dò:
      + Nếu thành công -> chuyển về CLOSED (bình thường).
      + Nếu thất bại -> quay lại OPEN thêm 1 chu kỳ cooldown.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 180.0,
        expected_exceptions: Tuple[type, ...] = (Exception,)
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.time()
        self.total_calls = 0
        self.total_successes = 0
        self.total_failures = 0
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Kiểm tra xem request hiện tại có được phép gọi hay không"""
        with self._lock:
            now = time.time()
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if self.last_failure_time and (now - self.last_failure_time >= self.recovery_timeout):
                    self.state = CircuitState.HALF_OPEN
                    self.last_state_change = now
                    logger.info(f"🔄 Circuit Breaker [{self.name}] chuyển sang HALF_OPEN (thử nghiệm phục hồi)...")
                    return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                # Chỉ cho phép 1 request thử nghiệm
                return True

            return False

    def record_success(self):
        """Ghi nhận 1 lần gọi thành công"""
        with self._lock:
            self.total_calls += 1
            self.total_successes += 1
            if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info(f"✅ Circuit Breaker [{self.name}] đã phục hồi hoàn toàn -> chuyển về CLOSED.")
                self.state = CircuitState.CLOSED
                self.last_state_change = time.time()
            self.failure_count = 0

    def record_failure(self, exc: Optional[Exception] = None):
        """Ghi nhận 1 lần gọi thất bại"""
        with self._lock:
            now = time.time()
            self.total_calls += 1
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = now

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.last_state_change = now
                logger.warning(
                    f"⚠️ Circuit Breaker [{self.name}] thử nghiệm thất bại -> quay lại OPEN "
                    f"(cooldown {self.recovery_timeout}s). Lỗi: {exc}"
                )
            elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_state_change = now
                logger.error(
                    f"🚨 Circuit Breaker [{self.name}] ĐÃ NGẮT (OPEN) sau {self.failure_count} lỗi liên tiếp! "
                    f"Tạm ngưng kết nối {self.recovery_timeout}s. Lỗi gần nhất: {exc}"
                )

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Thực thi hàm qua bảo vệ của Circuit Breaker"""
        if not self.can_execute():
            remaining = max(0.0, (self.last_failure_time or 0) + self.recovery_timeout - time.time())
            raise CircuitBreakerOpenException(self.name, remaining)

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except self.expected_exceptions as e:
            self.record_failure(e)
            raise

    def get_status(self) -> Dict:
        """Lấy thông tin trạng thái hiện tại của Circuit Breaker"""
        with self._lock:
            now = time.time()
            remaining_cooldown = 0.0
            if self.state == CircuitState.OPEN and self.last_failure_time:
                remaining_cooldown = max(0.0, self.last_failure_time + self.recovery_timeout - now)

            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "remaining_cooldown": round(remaining_cooldown, 1),
                "total_calls": self.total_calls,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
            }

    def reset(self):
        """Khôi phục thủ công về trạng thái CLOSED ban đầu"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None
            self.last_state_change = time.time()


def retry_with_backoff(
    retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    exceptions: Tuple[type, ...] = (Exception,),
    circuit_breaker: Optional[CircuitBreaker] = None
):
    """
    Decorator tự động thử lại với Exponential Backoff (1s -> 2s -> 4s...)
    và tích hợp sẵn với Circuit Breaker.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Nếu có Circuit Breaker, kiểm tra trước
            if circuit_breaker and not circuit_breaker.can_execute():
                remaining = max(0.0, (circuit_breaker.last_failure_time or 0) + circuit_breaker.recovery_timeout - time.time())
                raise CircuitBreakerOpenException(circuit_breaker.name, remaining)

            delay = initial_delay
            last_exc = None

            for attempt in range(1, retries + 1):
                try:
                    res = func(*args, **kwargs)
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    return res
                except exceptions as e:
                    last_exc = e
                    if attempt == retries:
                        if circuit_breaker:
                            circuit_breaker.record_failure(e)
                        logger.warning(
                            f"❌ [{func.__name__}] Thất bại toàn bộ sau {retries} lần thử. Lỗi cuối: {e}"
                        )
                        raise

                    actual_delay = min(delay, max_delay)
                    logger.warning(
                        f"⚠️ [{func.__name__}] Lần thử {attempt}/{retries} lỗi: {e}. "
                        f"Thử lại sau {actual_delay:.1f}s..."
                    )
                    time.sleep(actual_delay)
                    delay *= backoff_factor

            if last_exc:
                raise last_exc
        return wrapper
    return decorator


# Các Circuit Breakers định danh sẵn cho từng dịch vụ bên thứ ba
shopee_circuit_breaker = CircuitBreaker("ShopeeAPI", failure_threshold=5, recovery_timeout=180.0)
lazada_circuit_breaker = CircuitBreaker("LazadaAPI", failure_threshold=5, recovery_timeout=180.0)
telegram_circuit_breaker = CircuitBreaker("TelegramBotAPI", failure_threshold=5, recovery_timeout=120.0)
tinyurl_circuit_breaker = CircuitBreaker("TinyURL_API", failure_threshold=5, recovery_timeout=120.0)

ALL_CIRCUIT_BREAKERS: Dict[str, CircuitBreaker] = {
    "shopee": shopee_circuit_breaker,
    "lazada": lazada_circuit_breaker,
    "telegram": telegram_circuit_breaker,
    "tinyurl": tinyurl_circuit_breaker,
}


def get_all_resilience_status() -> Dict[str, Dict]:
    """Trả về trạng thái của tất cả Circuit Breakers trong hệ thống"""
    return {k: cb.get_status() for k, cb in ALL_CIRCUIT_BREAKERS.items()}
