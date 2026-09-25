from abc import ABC, abstractmethod
from typing import Dict, Optional, Any

class BaseAffiliateProvider(ABC):
    """Lớp cơ sở trừu tượng cho tất cả các nhà cung cấp Affiliate (Shopee, Lazada, Tiki...)"""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Tên sàn ('SHOPEE', 'LAZADA', ...)"""
        pass

    @abstractmethod
    def is_match_url(self, url: str) -> bool:
        """Kiểm tra URL này có thuộc về sàn này hay không"""
        pass

    @abstractmethod
    def convert_to_affiliate(self, original_url: str, channel: str = "telegram", sub_id: str = "") -> str:
        """Chuyển đổi URL sản phẩm thành link Affiliate hoa hồng của sàn kèm Sub-ID tracking"""
        pass

    @abstractmethod
    def extract_item_id(self, url: str) -> Optional[str]:
        """Trích xuất ID định danh sản phẩm từ URL"""
        pass

    @abstractmethod
    def verify_deal_freshness(self, deal: Dict) -> bool:
        """Kiểm tra sản phẩm còn hàng và còn giá khuyến mại hay không"""
        pass
