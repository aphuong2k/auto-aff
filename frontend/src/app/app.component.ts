import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { interval, Subscription } from 'rxjs';

interface Stats {
  categories_count: number;
  deals_today: number;
  deals_total: number;
  deals_shopee: number;
  deals_lazada: number;
  groups_total: number;
  groups_pending: number;
  groups_approved: number;
  groups_discovered: number;
  subscribers_count: number;
  total_commission_vnd: number;
  last_run: string | null;
  is_running: boolean;
  last_error: string | null;
  schedule: string;
}

interface HealthCheck {
  ready: boolean;
  shopee_configured: boolean;
  lazada_configured?: boolean;
  telegram_configured: boolean;
  facebook_configured: boolean;
  issues: string[];
}

interface ScheduleConfig {
  enabled: boolean;
  time: string;
  cats: number;
  next_run_display?: string;
}

interface Deal {
  item_id: string;
  category_name: string;
  name: string;
  price_original: number;
  price_sale: number;
  discount_percent: number;
  rating_star: number;
  historical_sold: number;
  deal_score: number;
  item_url: string;
  aff_url: string;
  image_url: string;
  created_date: string;
  local_image?: string;
  price_badge?: string;
  has_stamped_image?: boolean;
  stamped_image_url?: string;
  platform?: string;
  is_stale?: number;
  commission_rate?: number;
  is_extra?: number;
}

interface ClickAnalytics {
  total_clicks: number;
  channels: { channel: string; clicks: number }[];
  top_items: { item_id: string; name: string; price_sale: number; clicks: number; local_image?: string }[];
  daily_trend: { date: string; clicks: number }[];
}

interface SeedingHistoryItem {
  id: number;
  group_id: string;
  group_name?: string;
  item_id: string;
  deal_name?: string;
  comment_text: string;
  target_post_url?: string;
  posted_at: string;
  status: string;
}

interface FbGroup {
  group_id: string;
  name: string;
  url: string;
  category_name: string;
  members_count: number;
  status: 'DISCOVERED' | 'PENDING' | 'APPROVED' | 'REJECTED';
  last_posted_at: string | null;
  matched_deal?: Deal;
  category_deals_count?: number;
}

interface LearnedKeyword {
  id: number;
  category_name: string;
  keyword: string;
  source_group_name: string;
  frequency: number;
  last_used_at: string;
}

interface PromotionSlot {
  slot: string;
  title: string;
  highlight: string;
  banner?: string;
  status: 'UPCOMING' | 'ACTIVE' | 'PASSED';
  is_reminded_today: boolean;
}

interface VoucherItem {
  code: string;
  desc: string;
  badge: string;
}

interface PromotionResponse {
  campaign: { type: string; name: string; tagline: string };
  upcoming_slot: { slot: string; title: string };
  active_slot: { slot: string; title: string };
  slots: PromotionSlot[];
  vouchers: VoucherItem[];
  package: {
    campaign_name: string;
    slot_time: string;
    slot_title: string;
    aff_url: string;
  };
}

interface SaleReminderConfig {
  enabled: boolean;
  remind_before_minutes: number;
  slots: string[];
}

interface SystemConfig {
  shopee_app_id: string;
  shopee_secret: string;
  shopee_cookie: string;
  shopee_aff_cookie?: string;
  lazada_app_key?: string;
  lazada_app_secret?: string;
  lazada_aff_cookie?: string;
  lazada_tracking_url?: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
  fb_account_cookie: string;
  fb_chrome_profile_path: string;
  min_rating_star: number;
  min_historical_sold: number;
  min_discount_percent: number;
  max_groups_per_day: number;
  top_deals_per_category: number;
  community_invite_url?: string;
  community_name?: string;
  redirect_mode?: string;
  redirect_base_url?: string;
  api_admin_key?: string;
}

interface PostedLogItem {
  id: number;
  type: 'POST' | 'COMMENT';
  group_name: string;
  group_url?: string;
  target_url?: string;
  item_id?: string;
  item_name?: string;
  content_snippet?: string;
  image_path?: string;
  status: string;
  posted_at: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit, OnDestroy {
  apiUrl = 'http://localhost:8000/api';
  activeTab: 'dashboard' | 'deals' | 'marketing' | 'settings' | 'logs' = 'dashboard';
  dealsSubTab: 'deals' | 'promotions' | 'vouchers' = 'deals';
  marketingSubTab: 'social_copilot' | 'posts' | 'seeding' | 'groups' = 'social_copilot';

  // Trợ Lý Lan Tỏa Mạng Xã Hội (Social Outreach Copilot)
  selectedSocialDeal: any = null;
  selectedSocialAngle: 'review' | 'loss_leader' | 'price_compare' | 'flash_sale' = 'review';
  selectedSocialChannel: 'fb_feed' | 'fb_comment' | 'social' | 'fb_profile' = 'fb_feed';
  selectedTargetFbGroup: any = null;
  socialGeneratedPack: any = null;
  loadingSocialPack = false;
  socialSearchTerm: string = '';

  // Bộ lọc loại deal (Tất cả, 1K kích cookie, Hoa hồng khủng)
  dealTypeFilter: 'ALL' | 'LOSS_LEADER' | 'EXTRA' = 'ALL';

  // Voucher Codes & Pro Real-world Campaigns
  voucherCodes: any[] = [];
  campaignLinks: any = {
    wallet_url: 'https://s.shopee.vn/1LPJSANV7v',
    banner_1_url: 'https://s.shopee.vn/6q0WqKvmkf',
    banner_2_url: 'https://s.shopee.vn/7AdjQWuTmi',
    flat_deal_url: 'https://s.shopee.vn/5q8Qf8NVyC'
  };
  promoGeneratedPosts: any = null;
  newVoucher = {
    code: '',
    discount_desc: '',
    apply_url: '',
    category_filter: 'ALL',
    voucher_type: 'MANUAL',
    min_order: 0
  };
  selectedPromoPostTab: 'manual' | 'back' | 'high_value' | 'flat' = 'manual';
  publishingPromo = false;
  selectedGroupForPromo: string = '';

  stats: Stats = {
    categories_count: 0,
    deals_today: 0,
    deals_total: 0,
    deals_shopee: 0,
    deals_lazada: 0,
    groups_total: 0,
    groups_pending: 0,
    groups_approved: 0,
    groups_discovered: 0,
    subscribers_count: 0,
    total_commission_vnd: 0,
    last_run: null,
    is_running: false,
    last_error: null,
    schedule: '08:00 (Hàng ngày)'
  };

  health: HealthCheck = {
    ready: true,
    shopee_configured: false,
    lazada_configured: false,
    telegram_configured: false,
    facebook_configured: false,
    issues: []
  };

  schedule: ScheduleConfig = {
    enabled: false,
    time: '08:00',
    cats: 3,
    next_run_display: 'Đã tạm dừng (Chỉ chạy thủ công)'
  };

  workflowReports: any[] = [];
  loadingWorkflowReports = false;
  runningWorkflowStep: string | null = null;
  workflowCats: number = 3;

  config: SystemConfig = {
    shopee_app_id: '',
    shopee_secret: '',
    shopee_cookie: '',
    shopee_aff_cookie: '',
    lazada_app_key: '',
    lazada_app_secret: '',
    lazada_aff_cookie: '',
    lazada_tracking_url: '',
    telegram_bot_token: '',
    telegram_chat_id: '',
    fb_account_cookie: '',
    fb_chrome_profile_path: '',
    min_rating_star: 4.6,
    min_historical_sold: 500,
    min_discount_percent: 15,
    max_groups_per_day: 3,
    top_deals_per_category: 3,
    community_invite_url: '',
    community_name: 'Hội Săn Deal Shopee VIP',
    redirect_mode: 'direct',
    redirect_base_url: '',
    api_admin_key: ''
  };

  deals: Deal[] = [];
  groups: FbGroup[] = [];
  groupsFilterTab: 'ALL' | 'APPROVED' | 'DISCOVERED' | 'PENDING' = 'ALL';
  syncingGroups = false;
  showAddGroupModal = false;
  newGroup = {
    url: '',
    name: '',
    category_name: 'Cộng Đồng Chung',
    status: 'APPROVED' as 'APPROVED' | 'DISCOVERED' | 'PENDING',
    members_count: 10000
  };

  get approvedGroups(): FbGroup[] {
    return this.groups.filter(g => g.status === 'APPROVED');
  }

  get pendingGroups(): FbGroup[] {
    return this.groups.filter(g => g.status === 'PENDING');
  }

  get discoveredGroups(): FbGroup[] {
    return this.groups.filter(g => g.status === 'DISCOVERED');
  }

  get discoveredAndPendingGroups(): FbGroup[] {
    return this.groups.filter(g => g.status === 'DISCOVERED' || g.status === 'PENDING');
  }

  // Gradual Posting & Matching State
  gradualPostingState: any = { is_running: false, total_target: 0, completed: 0, current_group: '', status: 'IDLE' };
  gradualMaxGroups: number = 3;
  gradualDelaySeconds: number = 180;
  postingSingleGroup: { [groupId: string]: boolean } = {};
  gradualPollingTimer: any = null;
  selectedGroupCategoryFilter: string = 'ALL';

  get filteredApprovedGroups(): FbGroup[] {
    const list = this.groups.filter(g => g.status === 'APPROVED');
    if (this.selectedGroupCategoryFilter === 'ALL') return list;
    return list.filter(g => g.category_name === this.selectedGroupCategoryFilter);
  }

  categoryInventory: { [cat: string]: number } = {};
  showPickDealModal = false;
  selectedGroupForPicking: any = null;
  dealsForCategory: Deal[] = [];
  loadingCategoryDeals = false;
  availableCategories = [
    'Thời Trang Nam',
    'Thời Trang Nữ',
    'Thiết Bị Điện Tử',
    'Săn Deal Tổng Hợp',
    'Nhà Cửa & Đời Sống',
    'Cộng Đồng Chung'
  ];

  learnedKeywords: LearnedKeyword[] = [];
  promotionData?: PromotionResponse;
  saleReminderConfig: SaleReminderConfig = { enabled: true, remind_before_minutes: 15, slots: [] };
  selectedReminderSlot = '';
  sendingReminder = false;
  testingShopeeAff = false;

  generalPosts?: {
    post_roundup: string;
    post_schedule: string;
    post_tips: string;
    community_url: string;
    community_name: string;
    deal_count: number;
  };
  generatingCollage = false;
  collageImageUrl = 'http://localhost:8000/api/outreach/collage-image';
  generatingHeaderBanner = false;
  headerBannerImageUrl = 'http://localhost:8000/api/outreach/header-banner-image';

  postedLogs: PostedLogItem[] = [];
  postedLogsLoading = false;
  newPostLog = {
    type: 'POST',
    group_name: '',
    target_url: '',
    item_name: '',
    content_snippet: ''
  };
  showAddLogModal = false;

  clickAnalytics?: ClickAnalytics;
  seedingHistory: SeedingHistoryItem[] = [];
  seedingLoading = false;
  selectedPreviewDeal?: Deal;
  showImageModal = false;

  logsContent = 'Đang tải nhật ký...';
  autoRefreshLogs = true;
  seedingLogsContent = 'Đang nạp nhật ký seeding...';
  autoRefreshSeedingLogs = true;
  pollSub?: Subscription;

  toastMessage = '';
  toastType: 'success' | 'error' | 'info' = 'info';
  showToast = false;

  testingShopee = false;
  testingTelegram = false;
  testingLazada = false;

  // Bộ lọc sàn & độ tươi deals
  dealPlatformFilter: 'ALL' | 'SHOPEE' | 'LAZADA' = 'ALL';
  dealFreshnessFilter: 'ALL' | 'FRESH' | 'STALE' = 'ALL';
  verifyingAllDeals = false;

  // Dữ liệu Hoa Hồng & Doanh thu
  commissions: any[] = [];
  commissionStats: any = null;
  loadingCommissions = false;
  subscribers: any[] = [];
  importingCsv = false;
  csvPlatform: 'SHOPEE' | 'LAZADA' = 'SHOPEE';

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.fetchStats();
    this.fetchHealth();
    this.fetchSchedule();
    this.fetchConfig();
    this.fetchDeals();
    this.fetchGroups();
    this.fetchLearnedKeywords();
    this.fetchPromotions();
    this.fetchPromotionConfig();
    this.fetchClickAnalytics();
    this.fetchSeedingHistory();
    this.fetchGeneralPosts();
    this.fetchPostedLogs();
    this.fetchCommissions();
    this.fetchVoucherCodes();
    this.fetchGeneratedPromoPosts();
    this.fetchWorkflowReports();

    this.pollSub = interval(3500).subscribe(() => {
      this.fetchStats();
      this.fetchHealth();
      if (this.activeTab === 'settings' || this.stats.is_running || this.runningWorkflowStep) {
        this.fetchWorkflowReports();
      }
      if (this.activeTab === 'logs' && this.autoRefreshLogs) {
        this.fetchLogs();
      }
      if (this.activeTab === 'marketing' && this.autoRefreshSeedingLogs && this.marketingSubTab === 'seeding') {
        this.fetchSeedingLogs();
      }
    });
  }

  ngOnDestroy(): void {
    if (this.pollSub) {
      this.pollSub.unsubscribe();
    }
  }

  switchTab(tab: string): void {
    // Chuyển hướng thông minh các tab cũ về Hub nghiệp vụ tương ứng
    if (tab === 'schedule') {
      this.activeTab = 'settings';
      this.fetchSchedule();
      this.fetchConfig();
      return;
    }
    if (tab === 'promotions') {
      this.activeTab = 'deals';
      this.dealsSubTab = 'promotions';
      this.fetchPromotions();
      this.fetchPromotionConfig();
      return;
    }
    if (tab === 'groups') {
      this.activeTab = 'marketing';
      this.marketingSubTab = 'groups';
      this.fetchGroups();
      this.fetchLearnedKeywords();
      return;
    }
    if (tab === 'commissions' || tab === 'analytics') {
      this.activeTab = 'dashboard';
      this.fetchCommissions();
      this.fetchClickAnalytics();
      return;
    }

    this.activeTab = tab as any;
    if (tab === 'dashboard') {
      this.fetchStats();
      this.fetchCommissions();
      this.fetchClickAnalytics();
      this.fetchDeals();
    }
    if (tab === 'deals') {
      this.fetchDeals();
      this.fetchPromotions();
      this.fetchPromotionConfig();
      this.fetchVoucherCodes();
      this.fetchGeneratedPromoPosts();
    }
    if (tab === 'marketing') {
      this.fetchGeneralPosts();
      this.fetchGroups();
      this.fetchLearnedKeywords();
      this.fetchPostedLogs();
      this.fetchSeedingHistory();
      this.fetchSeedingLogs();
    }
    if (tab === 'settings') {
      this.fetchConfig();
      this.fetchSchedule();
    }
    if (tab === 'logs') {
      this.fetchLogs();
    }
  }

  setDealsSubTab(sub: 'deals' | 'promotions' | 'vouchers'): void {
    this.dealsSubTab = sub;
    if (sub === 'deals') this.fetchDeals();
    if (sub === 'promotions') {
      this.fetchPromotions();
      this.fetchPromotionConfig();
    }
    if (sub === 'vouchers') {
      this.fetchVoucherCodes();
      this.fetchGeneratedPromoPosts();
    }
  }

  setMarketingSubTab(sub: 'social_copilot' | 'posts' | 'seeding' | 'groups'): void {
    this.marketingSubTab = sub;
    if (sub === 'social_copilot') {
      if (!this.selectedSocialDeal && this.deals.length > 0) {
        this.selectedSocialDeal = this.deals[0];
      }
      if (this.selectedSocialDeal) {
        this.fetchSocialPack();
      }
    }
    if (sub === 'posts') this.fetchGeneralPosts();
    if (sub === 'seeding') {
      this.fetchSeedingHistory();
      this.fetchSeedingLogs();
    }
    if (sub === 'groups') {
      this.fetchGroups();
      this.fetchLearnedKeywords();
      this.fetchPostedLogs();
      this.fetchGradualPostingStatus();
    }
  }

  fetchClickAnalytics(): void {
    this.http.get<ClickAnalytics>(`${this.apiUrl}/analytics/clicks`).subscribe({
      next: (res) => (this.clickAnalytics = res),
      error: (err) => console.error('Lỗi tải thống kê click:', err)
    });
  }

  fetchSeedingHistory(): void {
    this.http.get<{ history: SeedingHistoryItem[] }>(`${this.apiUrl}/outreach/seed-comments/history`).subscribe({
      next: (res) => (this.seedingHistory = res.history || []),
      error: (err) => console.error('Lỗi tải lịch sử seeding:', err)
    });
  }

  fetchSeedingLogs(): void {
    this.http.get<{ logs: string; total_lines?: number }>(`${this.apiUrl}/outreach/seeding-logs?lines=150`).subscribe({
      next: (res) => (this.seedingLogsContent = res.logs || 'Chưa có nhật ký seeding.'),
      error: (err) => console.error('Lỗi nạp nhật ký seeding:', err)
    });
  }

  clearSeedingLogs(): void {
    this.http.post<any>(`${this.apiUrl}/outreach/seeding-logs/clear`, {}).subscribe({
      next: () => {
        this.seedingLogsContent = 'Đã xóa trắng nhật ký Facebook Seeding.';
        this.triggerToast('Đã xóa sạch nhật ký seeding!', 'info');
      }
    });
  }

  copyCommentText(text: string): void {
    navigator.clipboard.writeText(text).then(() => {
      this.triggerToast('Đã sao chép nội dung bình luận vào bộ nhớ tạm!', 'success');
    }).catch(() => {
      this.triggerToast('Không thể sao chép!', 'error');
    });
  }

  triggerCommentSeeding(): void {
    this.seedingLoading = true;
    this.fetchSeedingLogs();
    this.http.post<any>(`${this.apiUrl}/outreach/seed-comments?max_groups=3`, {}).subscribe({
      next: (res) => {
        this.seedingLoading = false;
        this.triggerToast(res.message, 'success');
        this.fetchSeedingHistory();
        this.fetchStats();
        this.fetchSeedingLogs();
      },
      error: (err) => {
        this.seedingLoading = false;
        this.triggerToast(err.error?.detail || err.message || 'Lỗi khi gieo bình luận!', 'error');
        this.fetchSeedingLogs();
      }
    });
  }

  get backendBaseUrl(): string {
    if (this.apiUrl && this.apiUrl.startsWith('http')) {
      try {
        const u = new URL(this.apiUrl);
        return `${u.protocol}//${u.host}`;
      } catch {
        return 'http://localhost:8000';
      }
    }
    return '';
  }

  getDealImageUrl(deal: any): string {
    if (!deal) return '';
    if (deal.stamped_image_url && deal.stamped_image_url.startsWith('http')) {
      return deal.stamped_image_url;
    }
    const itemId = deal.item_id;
    if (itemId) {
      return `${this.backendBaseUrl}/api/deals/image/${itemId}`;
    }
    return deal.image_url || '';
  }

  onImageError(event: Event, deal?: any): void {
    const target = event.target as HTMLImageElement;
    if (!target) return;

    // Nếu ảnh banner server lỗi, thử nạp trực tiếp ảnh gốc Shopee CDN
    if (deal && deal.image_url && target.src !== deal.image_url && !target.src.includes('susercontent.com')) {
      target.src = deal.image_url;
      return;
    }

    // Nếu cả ảnh gốc cũng không có/lỗi, hiển thị ảnh placeholder SVG Flash Sale sắc nét
    target.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%231e293b"/><stop offset="100%" stop-color="%230f172a"/></linearGradient></defs><rect width="400" height="400" fill="url(%23g)" rx="16"/><circle cx="200" cy="170" r="55" fill="%23f97316" fill-opacity="0.15"/><path d="M200 130 L180 175 L202 175 L195 210 L225 165 L202 165 Z" fill="%23f97316"/><text x="200" y="255" fill="%23f1f5f9" font-size="16" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-weight="700" text-anchor="middle">SHOPEE FLASH SALE</text><text x="200" y="280" fill="%2394a3b8" font-size="13" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" text-anchor="middle">Chính Hãng • Giá Tốt</text></svg>';
  }

  openImagePreview(deal: Deal): void {
    this.selectedPreviewDeal = deal;
    this.showImageModal = true;
  }

  closeImageModal(): void {
    this.showImageModal = false;
    this.selectedPreviewDeal = undefined;
  }

  copyBridgeLink(itemId: string, directUrl?: string): void {
    const link = directUrl || `${this.backendBaseUrl}/r/${itemId}?channel=fb_manual`;
    navigator.clipboard.writeText(link).then(() => {
      this.triggerToast('Đã sao chép link sản phẩm vào bộ nhớ tạm!', 'success');
    }).catch(() => {
      this.triggerToast(`Link: ${link}`, 'info');
    });
  }

  fetchGeneralPosts(): void {
    this.http.get<any>(`${this.apiUrl}/outreach/general-posts`).subscribe({
      next: (res) => (this.generalPosts = res),
      error: (err) => console.error('Lỗi tải bài đăng nhóm chung:', err)
    });
  }

  generateCollage(): void {
    this.generatingCollage = true;
    this.http.post<any>(`${this.apiUrl}/outreach/generate-collage`, {}).subscribe({
      next: (res) => {
        this.generatingCollage = false;
        this.collageImageUrl = `${this.apiUrl}/outreach/collage-image?t=${Date.now()}`;
        this.triggerToast(res.message, 'success');
      },
      error: (err) => {
        this.generatingCollage = false;
        this.triggerToast(err.message || 'Lỗi khi tạo ảnh ghép!', 'error');
      }
    });
  }

  generateHeaderBanner(): void {
    this.generatingHeaderBanner = true;
    this.http.post<any>(`${this.apiUrl}/outreach/generate-header-banner`, {}).subscribe({
      next: (res) => {
        this.generatingHeaderBanner = false;
        this.headerBannerImageUrl = `${this.apiUrl}/outreach/header-banner-image?t=${Date.now()}`;
        this.triggerToast(res.message, 'success');
      },
      error: (err) => {
        this.generatingHeaderBanner = false;
        this.triggerToast(err.message || 'Lỗi khi tạo ảnh tiêu đề!', 'error');
      }
    });
  }

  fetchPostedLogs(): void {
    this.postedLogsLoading = true;
    this.http.get<{ logs: PostedLogItem[] }>(`${this.apiUrl}/logs/posted`).subscribe({
      next: (res) => {
        this.postedLogsLoading = false;
        this.postedLogs = res.logs || [];
      },
      error: (err) => {
        this.postedLogsLoading = false;
        console.error('Lỗi tải lịch sử bài đăng:', err);
      }
    });
  }

  addPostedLog(): void {
    if (!this.newPostLog.group_name || !this.newPostLog.target_url) {
      this.triggerToast('Vui lòng nhập Tên nhóm và Link bài viết Facebook!', 'error');
      return;
    }
    this.http.post<any>(`${this.apiUrl}/logs/posted`, this.newPostLog).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.showAddLogModal = false;
        this.newPostLog = { type: 'POST', group_name: '', target_url: '', item_name: '', content_snippet: '' };
        this.fetchPostedLogs();
      },
      error: (err) => this.triggerToast(err.message || 'Lỗi lưu log bài đăng!', 'error')
    });
  }

  deletePostedLog(id: number): void {
    if (!confirm('Bạn có chắc muốn xóa bản ghi này?')) return;
    this.http.delete<any>(`${this.apiUrl}/logs/posted/${id}`).subscribe({
      next: () => {
        this.triggerToast('Đã xóa log bài đăng thành công!', 'info');
        this.fetchPostedLogs();
      },
      error: (err) => this.triggerToast(err.message || 'Lỗi khi xóa log!', 'error')
    });
  }

  copyPostText(text?: string, title: string = 'Nội dung'): void {
    if (!text) {
      this.triggerToast('Chưa có nội dung để sao chép!', 'info');
      return;
    }
    navigator.clipboard.writeText(text).then(() => {
      this.triggerToast(`✅ Đã sao chép [${title}] vào bộ nhớ tạm! Sẵn sàng dán lên Facebook.`, 'success');
    }).catch(() => {
      this.triggerToast('Vui lòng copy thủ công từ giao diện!', 'info');
    });
  }

  fetchPromotions(): void {
    this.http.get<PromotionResponse>(`${this.apiUrl}/promotions/today`).subscribe({
      next: (res) => {
        this.promotionData = res;
        if (!this.selectedReminderSlot && res.upcoming_slot) {
          this.selectedReminderSlot = res.upcoming_slot.slot;
        }
      },
      error: (err) => console.error('Lỗi tải khuyến mại:', err)
    });
  }

  fetchPromotionConfig(): void {
    this.http.get<SaleReminderConfig>(`${this.apiUrl}/promotions/config`).subscribe({
      next: (res) => (this.saleReminderConfig = res),
      error: (err) => console.error('Lỗi tải cấu hình nhắc sale:', err)
    });
  }

  savePromotionConfig(): void {
    this.http.post<any>(`${this.apiUrl}/promotions/config`, {
      enabled: this.saleReminderConfig.enabled,
      remind_before_minutes: this.saleReminderConfig.remind_before_minutes
    }).subscribe({
      next: (res) => this.triggerToast(res.message, 'success'),
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  triggerReminderNow(slot?: string): void {
    this.sendingReminder = true;
    const targetSlot = slot || this.selectedReminderSlot || '';
    this.http.post<any>(`${this.apiUrl}/promotions/remind-now?slot=${targetSlot}`, {}).subscribe({
      next: (res) => {
        this.sendingReminder = false;
        this.triggerToast(res.message, 'success');
        this.fetchPromotions();
      },
      error: (err) => {
        this.sendingReminder = false;
        this.triggerToast(err.message || 'Lỗi gửi bài nhắc!', 'error');
      }
    });
  }

  fetchVoucherCodes(): void {
    this.http.get<any>(`${this.apiUrl}/promotions/voucher-codes`).subscribe({
      next: (res) => {
        this.voucherCodes = res.vouchers || [];
        if (res.campaign_links) {
          this.campaignLinks = { ...this.campaignLinks, ...res.campaign_links };
        }
      },
      error: (err) => console.error('Lỗi tải danh sách voucher:', err)
    });
  }

  fetchGeneratedPromoPosts(): void {
    this.http.get<any>(`${this.apiUrl}/promotions/generated-posts`).subscribe({
      next: (res) => {
        this.promoGeneratedPosts = res;
      },
      error: (err) => console.error('Lỗi sinh bài đăng khuyến mại:', err)
    });
  }

  saveVoucherCode(): void {
    if (!this.newVoucher.code || !this.newVoucher.discount_desc) {
      this.triggerToast('Vui lòng nhập Mã voucher và Mô tả mức giảm!', 'error');
      return;
    }
    this.http.post<any>(`${this.apiUrl}/promotions/voucher-codes`, this.newVoucher).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.newVoucher = {
          code: '',
          discount_desc: '',
          apply_url: '',
          category_filter: 'ALL',
          voucher_type: 'MANUAL',
          min_order: 0
        };
        this.fetchVoucherCodes();
        this.fetchGeneratedPromoPosts();
      },
      error: (err) => this.triggerToast(err.message || 'Lỗi thêm mã voucher!', 'error')
    });
  }

  deleteVoucherCode(id: number): void {
    if (!confirm('Bạn có chắc chắn muốn xóa mã voucher này?')) return;
    this.http.delete<any>(`${this.apiUrl}/promotions/voucher-codes/${id}`).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'info');
        this.fetchVoucherCodes();
        this.fetchGeneratedPromoPosts();
      },
      error: (err) => this.triggerToast(err.message || 'Lỗi xóa voucher!', 'error')
    });
  }

  seedDemoVouchers(): void {
    this.http.post<any>(`${this.apiUrl}/promotions/voucher-codes/seed-demo`, {}).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchVoucherCodes();
        this.fetchGeneratedPromoPosts();
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  saveCampaignLinks(): void {
    this.http.post<any>(`${this.apiUrl}/promotions/campaign-links`, this.campaignLinks).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchGeneratedPromoPosts();
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  publishPromoPost(target: 'TELEGRAM' | 'FB_GROUP', content: string): void {
    if (!content) {
      this.triggerToast('Nội dung bài đăng đang trống!', 'error');
      return;
    }
    if (target === 'FB_GROUP' && !this.selectedGroupForPromo) {
      this.triggerToast('Vui lòng chọn nhóm Facebook muốn đăng bài!', 'error');
      return;
    }

    this.publishingPromo = true;
    this.triggerToast(`Đang bắn bài đăng lên ${target === 'TELEGRAM' ? 'Telegram' : 'Facebook'}...`, 'info');

    this.http.post<any>(`${this.apiUrl}/promotions/publish-post`, {
      target: target,
      group_id: this.selectedGroupForPromo || undefined,
      content: content
    }).subscribe({
      next: (res) => {
        this.publishingPromo = false;
        this.triggerToast(res.message || 'Đăng bài thành công!', 'success');
        this.fetchPostedLogs();
      },
      error: (err) => {
        this.publishingPromo = false;
        const msg = err.error?.detail || err.message || 'Lỗi khi đăng bài';
        this.triggerToast(`Lỗi: ${msg}`, 'error');
      }
    });
  }

  fetchLearnedKeywords(): void {
    this.http.get<{ keywords: LearnedKeyword[] }>(`${this.apiUrl}/keywords/learned`).subscribe({
      next: (res) => (this.learnedKeywords = res.keywords || []),
      error: (err) => console.error('Lỗi tải từ khóa tự học:', err)
    });
  }

  seedLearnedKeywords(): void {
    this.http.post<any>(`${this.apiUrl}/keywords/learned/seed`, {}).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchLearnedKeywords();
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  clearLearnedKeywords(): void {
    this.http.post<any>(`${this.apiUrl}/keywords/learned/clear`, {}).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'info');
        this.learnedKeywords = [];
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  fetchStats(): void {
    this.http.get<Stats>(`${this.apiUrl}/stats`).subscribe({
      next: (res) => (this.stats = res),
      error: () => console.warn('Chưa kết nối được Backend API')
    });
  }

  fetchHealth(): void {
    this.http.get<HealthCheck>(`${this.apiUrl}/health`).subscribe({
      next: (res) => (this.health = res),
      error: (err) => console.error(err)
    });
  }

  fetchSchedule(): void {
    this.http.get<ScheduleConfig>(`${this.apiUrl}/schedule`).subscribe({
      next: (res) => (this.schedule = res),
      error: (err) => console.error(err)
    });
  }

  saveSchedule(): void {
    this.http.post(`${this.apiUrl}/schedule`, this.schedule).subscribe({
      next: (res: any) => {
        this.triggerToast(res.message || 'Lưu lịch chạy thành công!', 'success');
        this.fetchStats();
      },
      error: (err) => this.triggerToast('Lỗi lưu lịch chạy: ' + err.message, 'error')
    });
  }

  fetchWorkflowReports(): void {
    this.loadingWorkflowReports = true;
    this.http.get<{ reports: any[] }>(`${this.apiUrl}/workflow/reports?limit=25`).subscribe({
      next: (res) => {
        this.workflowReports = res.reports || [];
        this.loadingWorkflowReports = false;
      },
      error: (err) => {
        this.loadingWorkflowReports = false;
        console.error('Lỗi nạp báo cáo tiến trình:', err);
      }
    });
  }

  runWorkflowStep(step: string): void {
    this.runningWorkflowStep = step;
    let url = '';
    let stepTitle = '';
    if (step === 'crawl') {
      url = `${this.apiUrl}/workflow/step/crawl?cats=${this.workflowCats || 3}`;
      stepTitle = 'Bước 1: Quét deal hot đa sàn';
    } else if (step === 'media') {
      url = `${this.apiUrl}/workflow/step/create-media`;
      stepTitle = 'Bước 2: Tạo banner Flash Sale & ảnh bài';
    } else if (step === 'telegram') {
      url = `${this.apiUrl}/workflow/step/telegram`;
      stepTitle = 'Bước 3: Bắn tin Kênh Telegram';
    } else if (step === 'fb') {
      url = `${this.apiUrl}/workflow/step/fb-outreach?max_groups=3`;
      stepTitle = 'Bước 4: Đăng bài dần vào nhóm Facebook';
    } else if (step === 'seeding') {
      url = `${this.apiUrl}/workflow/step/seeding?max_groups=3`;
      stepTitle = 'Bước 5: Gieo seeding kèm link Anti-Ban';
    }

    this.triggerToast(`Đang khởi chạy ${stepTitle}...`, 'info');
    this.http.post<any>(url, {}).subscribe({
      next: (res) => {
        this.runningWorkflowStep = null;
        this.triggerToast(res.message || `Hoàn tất ${stepTitle}!`, 'success');
        this.fetchWorkflowReports();
        this.fetchStats();
        if (step === 'crawl') {
          this.fetchDeals();
        } else if (step === 'fb' || step === 'seeding') {
          this.fetchPostedLogs();
        }
      },
      error: (err) => {
        this.runningWorkflowStep = null;
        const msg = err.error?.detail || err.message || 'Lỗi thực thi bước!';
        this.triggerToast(`Lỗi ${stepTitle}: ${msg}`, 'error');
        this.fetchWorkflowReports();
      }
    });
  }

  runWorkflowAll(): void {
    if (this.stats.is_running) {
      this.triggerToast('Hệ thống đang chạy tiến trình khác, vui lòng chờ!', 'info');
      return;
    }
    this.runningWorkflowStep = 'all';
    this.triggerToast('🚀 Đang kích hoạt toàn trình 5 bước tự động...', 'info');
    this.http.post<any>(`${this.apiUrl}/workflow/run-all?cats=${this.workflowCats || 3}`, {}).subscribe({
      next: (res) => {
        this.runningWorkflowStep = null;
        this.triggerToast(res.message || 'Đã kích hoạt toàn trình 5 bước!', 'success');
        this.stats.is_running = true;
        this.fetchWorkflowReports();
      },
      error: (err) => {
        this.runningWorkflowStep = null;
        this.triggerToast(err.error?.detail || err.message || 'Lỗi khởi động toàn trình!', 'error');
      }
    });
  }

  fetchDeals(): void {
    let url = `${this.apiUrl}/deals?limit=50`;
    if (this.dealPlatformFilter !== 'ALL') {
      url += `&platform=${this.dealPlatformFilter}`;
    }
    if (this.dealFreshnessFilter === 'FRESH') {
      url += `&is_stale=0`;
    } else if (this.dealFreshnessFilter === 'STALE') {
      url += `&is_stale=1`;
    }
    if (this.dealTypeFilter !== 'ALL') {
      url += `&deal_type=${this.dealTypeFilter}`;
    }
    this.http.get<Deal[]>(url).subscribe({
      next: (res) => {
        this.deals = res;
        if (!this.selectedSocialDeal && this.deals.length > 0) {
          this.selectedSocialDeal = this.deals[0];
          this.fetchSocialPack();
        }
      },
      error: (err) => console.error(err)
    });
  }

  setDealPlatformFilter(platform: 'ALL' | 'SHOPEE' | 'LAZADA'): void {
    this.dealPlatformFilter = platform;
    this.fetchDeals();
  }

  setDealFreshnessFilter(freshness: 'ALL' | 'FRESH' | 'STALE'): void {
    this.dealFreshnessFilter = freshness;
    this.fetchDeals();
  }

  setDealTypeFilter(type: 'ALL' | 'LOSS_LEADER' | 'EXTRA'): void {
    this.dealTypeFilter = type;
    this.fetchDeals();
  }

  // --- TRỢ LÝ TIẾP THỊ MẠNG XÃ HỘI (SOCIAL COPILOT METHODS) ---
  get filteredDealsForSocial(): Deal[] {
    if (!this.socialSearchTerm) return this.deals;
    const term = this.socialSearchTerm.toLowerCase();
    return this.deals.filter(d => (d.name && d.name.toLowerCase().includes(term)) || (d.category_name && d.category_name.toLowerCase().includes(term)));
  }

  selectDealForSocial(deal: any): void {
    this.selectedSocialDeal = deal;
    this.fetchSocialPack();
  }

  setSocialAngle(angle: 'review' | 'loss_leader' | 'price_compare' | 'flash_sale'): void {
    this.selectedSocialAngle = angle;
    this.fetchSocialPack();
  }

  setSocialChannel(channel: 'fb_feed' | 'fb_comment' | 'social' | 'fb_profile'): void {
    this.selectedSocialChannel = channel;
    this.fetchSocialPack();
  }

  fetchSocialPack(): void {
    if (!this.selectedSocialDeal) return;
    this.loadingSocialPack = true;
    const itemId = this.selectedSocialDeal.item_id;
    this.http.get<any>(`${this.apiUrl}/social/generate-pack?item_id=${itemId}&angle=${this.selectedSocialAngle}&channel=${this.selectedSocialChannel}`).subscribe({
      next: (res) => {
        this.loadingSocialPack = false;
        this.socialGeneratedPack = res;
      },
      error: (err) => {
        this.loadingSocialPack = false;
        console.error('Lỗi sinh social pack:', err);
      }
    });
  }

  openSocialCopilotForDeal(deal: Deal): void {
    this.selectedSocialDeal = deal;
    this.activeTab = 'marketing';
    this.marketingSubTab = 'social_copilot';
    if (deal.price_badge === 'LOSS_LEADER_1K' || deal.price_sale <= 15000) {
      this.selectedSocialAngle = 'loss_leader';
    } else {
      this.selectedSocialAngle = 'review';
    }
    this.fetchSocialPack();
    this.triggerToast(`Đã nạp deal [${deal.name.slice(0, 30)}...] vào Trợ lý Lan tỏa MXH!`, 'success');
  }

  copySocialCaption(): void {
    if (!this.socialGeneratedPack?.caption) return;
    navigator.clipboard.writeText(this.socialGeneratedPack.caption).then(() => {
      this.triggerToast('Đã sao chép nội dung bài viết (kèm link DeepLink & hashtag)!', 'success');
    }).catch(() => {
      this.triggerToast('Không thể sao chép văn bản!', 'error');
    });
  }

  copySocialShortLink(): void {
    if (!this.socialGeneratedPack) return;
    const link = this.socialGeneratedPack.target_link || this.socialGeneratedPack.direct_aff_url || this.selectedSocialDeal?.aff_url || this.selectedSocialDeal?.item_url || `${this.backendBaseUrl}${this.socialGeneratedPack.bridge_url}`;
    navigator.clipboard.writeText(link).then(() => {
      this.triggerToast('Đã sao chép link sản phẩm sàn trực tiếp!', 'success');
    }).catch(() => {
      this.triggerToast(`Link: ${link}`, 'info');
    });
  }

  openTargetFbGroupDirectly(): void {
    if (!this.selectedTargetFbGroup?.url) {
      this.triggerToast('Vui lòng chọn nhóm Facebook muốn đăng bài!', 'error');
      return;
    }
    this.copySocialCaption();
    window.open(this.selectedTargetFbGroup.url, '_blank');
    this.triggerToast(`Đã copy bài viết và mở nhóm [${this.selectedTargetFbGroup.name}]. Bạn chỉ cần dán bài và đính kèm ảnh!`, 'info');
  }

  fetchCategoryInventory(): void {
    this.http.get<{ [cat: string]: number }>(`${this.apiUrl}/deals/category-inventory`).subscribe({
      next: (res) => (this.categoryInventory = res || {}),
      error: (err) => console.error('Lỗi tải kho deal theo ngành:', err)
    });
  }

  fetchGroups(): void {
    this.fetchCategoryInventory();
    this.http.get<any[]>(`${this.apiUrl}/groups/with-matched-deals`).subscribe({
      next: (res) => (this.groups = res),
      error: () => {
        this.http.get<FbGroup[]>(`${this.apiUrl}/groups`).subscribe({
          next: (r) => (this.groups = r)
        });
      }
    });
  }

  updateGroupCategory(groupId: string, newCategory: string): void {
    this.http.post<any>(`${this.apiUrl}/groups/${groupId}/category`, { category_name: newCategory }).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchGroups();
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  openPickDealModal(group: any): void {
    this.selectedGroupForPicking = group;
    this.showPickDealModal = true;
    this.loadingCategoryDeals = true;
    const cat = group.category_name || 'Thời Trang Nam';
    this.http.get<Deal[]>(`${this.apiUrl}/deals/by-category?category=${encodeURIComponent(cat)}`).subscribe({
      next: (res) => {
        this.loadingCategoryDeals = false;
        this.dealsForCategory = res || [];
      },
      error: (err) => {
        this.loadingCategoryDeals = false;
        console.error('Lỗi nạp deal theo ngành:', err);
      }
    });
  }

  closePickDealModal(): void {
    this.showPickDealModal = false;
    this.selectedGroupForPicking = null;
    this.dealsForCategory = [];
  }

  postSpecificDealToGroup(deal: Deal): void {
    if (!this.selectedGroupForPicking) return;
    const group = this.selectedGroupForPicking;
    const gid = group.group_id;
    this.closePickDealModal();
    this.postingSingleGroup[gid] = true;
    this.triggerToast(`Đang đăng sản phẩm [${deal.name}] vào nhóm [${group.name}]...`, 'info');

    this.http.post<any>(`${this.apiUrl}/outreach/post-to-group`, { group_id: gid, deal_id: deal.item_id }).subscribe({
      next: (res) => {
        this.postingSingleGroup[gid] = false;
        this.triggerToast(res.message || `Đã đăng bài thành công vào nhóm [${group.name}]!`, 'success');
        this.fetchGroups();
        this.fetchPostedLogs();
      },
      error: (err) => {
        this.postingSingleGroup[gid] = false;
        const msg = err.error?.detail || err.message || 'Lỗi khi đăng bài';
        this.triggerToast(`Lỗi đăng bài [${group.name}]: ${msg}`, 'error');
      }
    });
  }

  syncJoinedGroups(): void {
    this.syncingGroups = true;
    this.triggerToast('Đang kết nối Facebook để quét danh sách nhóm đã tham gia...', 'info');
    this.http.post<any>(`${this.apiUrl}/groups/sync-joined`, {}).subscribe({
      next: (res) => {
        this.syncingGroups = false;
        this.triggerToast(res.message || 'Đồng bộ thành công nhóm Facebook!', 'success');
        this.fetchGroups();
        this.fetchStats();
      },
      error: (err) => {
        this.syncingGroups = false;
        const msg = err.error?.detail || err.message || 'Lỗi khi đồng bộ';
        this.triggerToast('Lỗi đồng bộ nhóm: ' + msg, 'error');
      }
    });
  }

  openAddGroupModal(): void {
    this.newGroup = {
      url: '',
      name: '',
      category_name: 'Cộng Đồng Chung',
      status: 'APPROVED',
      members_count: 10000
    };
    this.showAddGroupModal = true;
  }

  closeAddGroupModal(): void {
    this.showAddGroupModal = false;
  }

  submitAddGroup(): void {
    if (!this.newGroup.url) {
      this.triggerToast('Vui lòng nhập đường dẫn URL của nhóm Facebook!', 'error');
      return;
    }
    this.http.post<any>(`${this.apiUrl}/groups/add`, this.newGroup).subscribe({
      next: (res) => {
        this.triggerToast(res.message || 'Đã thêm nhóm thành công!', 'success');
        this.showAddGroupModal = false;
        this.fetchGroups();
        this.fetchStats();
      },
      error: (err) => {
        this.triggerToast('Lỗi khi thêm nhóm: ' + (err.error?.detail || err.message), 'error');
      }
    });
  }

  updateGroupStatus(groupId: string, newStatus: string): void {
    this.http.post<any>(`${this.apiUrl}/groups/${groupId}/status`, { status: newStatus }).subscribe({
      next: (res) => {
        this.triggerToast(res.message || 'Đã cập nhật trạng thái nhóm!', 'success');
        this.fetchGroups();
        this.fetchStats();
      },
      error: (err) => {
        this.triggerToast('Lỗi cập nhật: ' + err.message, 'error');
      }
    });
  }

  deleteGroup(groupId: string): void {
    if (!confirm('Bạn có chắc chắn muốn xóa nhóm này khỏi hệ thống?')) return;
    this.http.delete<any>(`${this.apiUrl}/groups/${groupId}`).subscribe({
      next: (res) => {
        this.triggerToast(res.message || 'Đã xóa nhóm!', 'info');
        this.fetchGroups();
        this.fetchStats();
      },
      error: (err) => {
        this.triggerToast('Lỗi xóa nhóm: ' + err.message, 'error');
      }
    });
  }

  fetchGradualPostingStatus(): void {
    this.http.get<any>(`${this.apiUrl}/outreach/gradual-posting-status`).subscribe({
      next: (res) => {
        this.gradualPostingState = res;
        if (res.is_running && !this.gradualPollingTimer) {
          this.gradualPollingTimer = setInterval(() => this.fetchGradualPostingStatus(), 3000);
        } else if (!res.is_running && this.gradualPollingTimer) {
          clearInterval(this.gradualPollingTimer);
          this.gradualPollingTimer = null;
          this.fetchGroups();
          this.fetchPostedLogs();
        }
      },
      error: (err) => console.error('Lỗi nạp trạng thái đăng bài dần:', err)
    });
  }

  startGradualPosting(): void {
    this.triggerToast('Đang khởi động tiến trình đăng bài dần vào các nhóm...', 'info');
    this.http.post<any>(`${this.apiUrl}/outreach/start-gradual-posting`, {
      max_groups: this.gradualMaxGroups,
      min_delay_seconds: this.gradualDelaySeconds,
      max_delay_seconds: Math.round(this.gradualDelaySeconds * 1.5)
    }).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchGradualPostingStatus();
      },
      error: (err) => this.triggerToast(err.error?.detail || err.message || 'Lỗi khởi động đăng bài dần!', 'error')
    });
  }

  stopGradualPosting(): void {
    this.http.post<any>(`${this.apiUrl}/outreach/stop-gradual-posting`, {}).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'info');
        this.fetchGradualPostingStatus();
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  postToSingleGroup(group: FbGroup): void {
    const gid = group.group_id;
    this.postingSingleGroup[gid] = true;
    this.triggerToast(`Đang tìm deal phù hợp và đăng bài vào nhóm [${group.name}]...`, 'info');

    this.http.post<any>(`${this.apiUrl}/outreach/post-to-group`, { group_id: gid }).subscribe({
      next: (res) => {
        this.postingSingleGroup[gid] = false;
        this.triggerToast(res.message || `Đã đăng bài thành công vào nhóm [${group.name}]!`, 'success');
        this.fetchGroups();
        this.fetchPostedLogs();
      },
      error: (err) => {
        this.postingSingleGroup[gid] = false;
        const msg = err.error?.detail || err.message || 'Lỗi khi đăng bài';
        this.triggerToast(`Lỗi đăng bài [${group.name}]: ${msg}`, 'error');
      }
    });
  }

  autoCategorizeGroups(): void {
    this.triggerToast('Đang tự động phân loại ngành hàng cho toàn bộ nhóm Facebook...', 'info');
    this.http.post<any>(`${this.apiUrl}/groups/auto-categorize`, {}).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchGroups();
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  fetchConfig(): void {
    this.http.get<SystemConfig>(`${this.apiUrl}/config`).subscribe({
      next: (res) => (this.config = res),
      error: (err) => console.error(err)
    });
  }

  saveConfig(): void {
    this.http.post(`${this.apiUrl}/config`, this.config).subscribe({
      next: (res: any) => {
        this.triggerToast(res.message || 'Lưu cấu hình thành công!', 'success');
        this.fetchHealth();
      },
      error: (err) => {
        this.triggerToast('Lỗi lưu cấu hình: ' + err.message, 'error');
      }
    });
  }

  testShopeeConnection(): void {
    this.testingShopee = true;
    this.http.post<any>(`${this.apiUrl}/test/shopee`, {}).subscribe({
      next: (res) => {
        this.testingShopee = false;
        this.triggerToast(res.message, 'success');
      },
      error: (err) => {
        this.testingShopee = false;
        this.triggerToast(err.error?.detail || err.message, 'error');
      }
    });
  }

  testShopeeAffConnection(): void {
    this.testingShopeeAff = true;
    this.http.post<any>(`${this.apiUrl}/test/shopee-aff`, {}).subscribe({
      next: (res) => {
        this.testingShopeeAff = false;
        this.triggerToast(res.message, 'success');
      },
      error: (err) => {
        this.testingShopeeAff = false;
        this.triggerToast(err.error?.detail || err.message, 'error');
      }
    });
  }

  testTelegramConnection(): void {
    this.testingTelegram = true;
    this.http.post<any>(`${this.apiUrl}/test/telegram`, {}).subscribe({
      next: (res) => {
        this.testingTelegram = false;
        this.triggerToast(res.message, 'success');
      },
      error: (err) => {
        this.testingTelegram = false;
        this.triggerToast(err.error?.detail || err.message, 'error');
      }
    });
  }

  fetchLogs(): void {
    this.http.get<{ logs: string }>(`${this.apiUrl}/logs?lines=200`).subscribe({
      next: (res) => (this.logsContent = res.logs),
      error: (err) => (this.logsContent = 'Lỗi kết nối đọc logs: ' + err.message)
    });
  }

  clearLogs(): void {
    this.http.post(`${this.apiUrl}/logs/clear`, {}).subscribe({
      next: () => {
        this.logsContent = '';
        this.triggerToast('Đã xóa sạch log!', 'info');
      }
    });
  }

  runWorkflowNow(): void {
    if (this.stats.is_running) {
      this.triggerToast('Hệ thống đang chạy một tiến trình khác!', 'info');
      return;
    }

    this.http.post(`${this.apiUrl}/run?cats=2`, {}).subscribe({
      next: (res: any) => {
        this.triggerToast(res.message || 'Đã kích hoạt chu trình!', 'success');
        this.stats.is_running = true;
        this.activeTab = 'logs';
        this.fetchLogs();
      },
      error: (err) => {
        this.triggerToast(err.error?.detail || 'Lỗi khởi động chu trình: ' + err.message, 'error');
      }
    });
  }

  clearDeals(): void {
    this.http.post(`${this.apiUrl}/deals/clear`, {}).subscribe({
      next: (res: any) => {
        this.deals = [];
        this.fetchStats();
        this.triggerToast(res.message || 'Đã xóa toàn bộ sản phẩm!', 'info');
      },
      error: (err) => this.triggerToast('Lỗi xóa sản phẩm: ' + err.message, 'error')
    });
  }

  fetchLossLeadersManual(): void {
    this.http.post<any>(`${this.apiUrl}/deals/fetch-loss-leaders?limit=3`, {}).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchDeals();
        this.fetchStats();
      },
      error: (err) => this.triggerToast(err.message || 'Lỗi khi cào deal mồi!', 'error')
    });
  }

  verifyDealFreshness(deal: Deal): void {
    this.http.post<any>(`${this.apiUrl}/deals/${deal.item_id}/verify-freshness`, {}).subscribe({
      next: (res) => {
        if (res.is_fresh) {
          this.triggerToast(`✅ Deal [${deal.name.slice(0, 30)}...] còn hàng & giá sale hợp lệ!`, 'success');
        } else {
          this.triggerToast(`⚠️ Deal [${deal.name.slice(0, 30)}...] đã hết hàng hoặc quay về giá gốc!`, 'error');
        }
      },
      error: (err) => this.triggerToast(err.message || 'Lỗi kiểm tra độ tươi', 'error')
    });
  }

  clearGroups(): void {
    this.http.post(`${this.apiUrl}/groups/clear`, {}).subscribe({
      next: (res: any) => {
        this.groups = [];
        this.fetchStats();
        this.triggerToast(res.message || 'Đã xóa toàn bộ nhóm Facebook!', 'info');
      },
      error: (err) => this.triggerToast('Lỗi xóa nhóm: ' + err.message, 'error')
    });
  }

  resetAllData(): void {
    this.http.post(`${this.apiUrl}/data/reset`, {}).subscribe({
      next: (res: any) => {
        this.deals = [];
        this.groups = [];
        this.fetchStats();
        this.triggerToast(res.message || 'Đã làm sạch toàn bộ dữ liệu sản phẩm & nhóm ảo!', 'info');
      },
      error: (err) => this.triggerToast('Lỗi dọn dẹp dữ liệu: ' + err.message, 'error')
    });
  }

  verifyAllDealsFreshness(): void {
    this.verifyingAllDeals = true;
    this.triggerToast('Đang tiến hành rà soát độ tươi của toàn bộ deal Shopee & Lazada...', 'info');
    this.http.post<any>(`${this.apiUrl}/deals/verify-all`, {}).subscribe({
      next: (res) => {
        this.verifyingAllDeals = false;
        this.triggerToast(`Hoàn tất: Đã kiểm tra ${res.total_checked} deals (${res.stale_count} đã hết hạn/hết hàng)`, 'success');
        this.fetchDeals();
        this.fetchStats();
      },
      error: (err) => {
        this.verifyingAllDeals = false;
        this.triggerToast(err.message || 'Lỗi kiểm tra độ tươi hàng loạt', 'error');
      }
    });
  }

  testLazadaConnection(): void {
    this.testingLazada = true;
    this.http.post<any>(`${this.apiUrl}/test/lazada`, {}).subscribe({
      next: (res) => {
        this.testingLazada = false;
        this.triggerToast(res.message, res.status === 'success' ? 'success' : 'info');
      },
      error: (err) => {
        this.testingLazada = false;
        this.triggerToast(err.error?.detail || err.message, 'error');
      }
    });
  }

  fetchCommissions(): void {
    this.loadingCommissions = true;
    this.http.get<any>(`${this.apiUrl}/commissions/stats`).subscribe({
      next: (stats) => {
        this.commissionStats = stats;
        this.http.get<any>(`${this.apiUrl}/commissions?limit=30`).subscribe({
          next: (res) => {
            this.commissions = res.commissions || [];
            this.loadingCommissions = false;
          },
          error: (err) => {
            this.loadingCommissions = false;
            console.error('Lỗi tải danh sách hoa hồng:', err);
          }
        });
      },
      error: (err) => {
        this.loadingCommissions = false;
        console.error('Lỗi tải thống kê hoa hồng:', err);
      }
    });
    this.http.get<any>(`${this.apiUrl}/subscribers?limit=50`).subscribe({
      next: (res) => (this.subscribers = res.subscribers || []),
      error: (err) => console.error('Lỗi tải danh sách subscriber:', err)
    });
  }

  seedDemoCommissions(): void {
    this.http.post<any>(`${this.apiUrl}/commissions/seed-demo`, {}).subscribe({
      next: (res) => {
        this.triggerToast(res.message, 'success');
        this.fetchCommissions();
        this.fetchStats();
      },
      error: (err) => this.triggerToast(err.message, 'error')
    });
  }

  onCsvFileSelected(event: any): void {
    const file: File = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e: any) => {
      const csvText = e.target.result;
      this.importingCsv = true;
      this.http.post<any>(`${this.apiUrl}/commissions/import`, {
        csv_text: csvText,
        platform: this.csvPlatform
      }).subscribe({
        next: (res) => {
          this.importingCsv = false;
          this.triggerToast(res.message, 'success');
          this.fetchCommissions();
          this.fetchStats();
        },
        error: (err) => {
          this.importingCsv = false;
          this.triggerToast(err.error?.detail || err.message, 'error');
        }
      });
    };
    reader.readAsText(file);
  }

  triggerToast(msg: string, type: 'success' | 'error' | 'info' = 'info'): void {
    this.toastMessage = msg;
    this.toastType = type;
    this.showToast = true;
    setTimeout(() => {
      this.showToast = false;
    }, 5000);
  }
}
