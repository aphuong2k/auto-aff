"""
Pydantic Models for FastAPI Request & Response Validation
=========================================================
"""

from typing import Optional, List
from pydantic import BaseModel


class SaleReminderConfigModel(BaseModel):
    enabled: bool
    remind_before_minutes: int


class ConfigModel(BaseModel):
    shopee_app_id: Optional[str] = ""
    shopee_secret: Optional[str] = ""
    shopee_cookie: Optional[str] = ""
    shopee_aff_cookie: Optional[str] = ""
    lazada_app_key: Optional[str] = ""
    lazada_app_secret: Optional[str] = ""
    lazada_aff_cookie: Optional[str] = ""
    lazada_tracking_url: Optional[str] = ""
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""
    fb_account_cookie: Optional[str] = ""
    fb_chrome_profile_path: Optional[str] = ""
    min_rating_star: Optional[float] = 4.6
    min_historical_sold: Optional[int] = 200
    min_discount_percent: Optional[int] = 15
    max_groups_per_day: Optional[int] = 3
    top_deals_per_category: Optional[int] = 3
    community_invite_url: Optional[str] = ""
    community_name: Optional[str] = "Hội Săn Deal Shopee VIP"
    redirect_mode: Optional[str] = "direct"
    redirect_base_url: Optional[str] = ""
    api_admin_key: Optional[str] = ""


class SubscriberRegisterModel(BaseModel):
    email: str
    telegram_id: Optional[str] = None
    platform_preference: Optional[str] = "ALL"
    category_preference: Optional[str] = "ALL"
    min_discount: Optional[int] = 30


class CommissionImportModel(BaseModel):
    platform: Optional[str] = "SHOPEE"
    csv_content: Optional[str] = ""
    csv_text: Optional[str] = ""


class PostedLogCreateModel(BaseModel):
    type: str = "POST"  # 'POST' hoặc 'COMMENT'
    group_name: str
    group_url: Optional[str] = ""
    target_url: Optional[str] = ""
    item_id: Optional[str] = ""
    item_name: Optional[str] = ""
    content_snippet: Optional[str] = ""
    image_path: Optional[str] = ""
    status: Optional[str] = "SUCCESS"


class ScheduleModel(BaseModel):
    enabled: bool
    time: str  # Định dạng "HH:MM" (VD: "08:00")
    cats: int  # Số ngành hàng quét mỗi lần


class SingleGroupPostRequest(BaseModel):
    group_id: str
    deal_id: Optional[str] = None
    account_id: Optional[object] = None


class GradualPostRequest(BaseModel):
    max_groups: Optional[int] = 3
    min_delay_seconds: Optional[int] = 60
    max_delay_seconds: Optional[int] = 120
    group_ids: Optional[List[str]] = None
    delay_seconds: Optional[int] = None
    account_id: Optional[object] = None


class RunWorkflowRequest(BaseModel):
    cats: Optional[int] = 2
    category_ids: Optional[List[int]] = None


class UpdateGroupCategoryRequest(BaseModel):
    category_name: str


class FbAccountCreateModel(BaseModel):
    name: str
    cookie: str
    profile_path: Optional[str] = ""
    daily_post_limit: Optional[int] = 3
    daily_join_limit: Optional[int] = 3
    proxy: Optional[str] = ""
    notes: Optional[str] = ""
    is_active: Optional[bool] = True


class FbAccountUpdateModel(BaseModel):
    name: Optional[str] = None
    cookie: Optional[str] = None
    profile_path: Optional[str] = None
    daily_post_limit: Optional[int] = None
    daily_join_limit: Optional[int] = None
    proxy: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None


class RetryNodeRequest(BaseModel):
    group_id: str


class CheckGroupHealthRequest(BaseModel):
    group_url: Optional[str] = None
    group_id: Optional[str] = None
    account_id: Optional[object] = None


class AddGroupRequest(BaseModel):
    url: str
    name: Optional[str] = ""
    category_name: Optional[str] = "Cộng Đồng Chung"
    status: Optional[str] = "APPROVED"
    members_count: Optional[int] = 10000


class UpdateGroupStatusRequest(BaseModel):
    status: str


class CreateVoucherCodeModel(BaseModel):
    code: str
    discount_desc: str
    apply_url: Optional[str] = ""
    category_filter: Optional[str] = "ALL"
    voucher_type: Optional[str] = "MANUAL"
    min_order: Optional[float] = 0


class UpdateCampaignLinksModel(BaseModel):
    wallet_url: Optional[str] = None
    banner_1_url: Optional[str] = None
    banner_2_url: Optional[str] = None
    flat_deal_url: Optional[str] = None


class PublishPromoPostModel(BaseModel):
    target: str  # 'TELEGRAM' or 'FB_GROUP'
    group_id: Optional[str] = None
    content: str
    post_type_label: Optional[str] = "Bài Khuyến Mại / Voucher"
    account_id: Optional[object] = None
