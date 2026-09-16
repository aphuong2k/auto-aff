import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { interval, Subscription } from 'rxjs';

interface Stats {
  categories_count: number;
  deals_today: number;
  deals_total: number;
  groups_total: number;
  groups_pending: number;
  groups_approved: number;
  groups_discovered: number;
  last_run: string | null;
  is_running: boolean;
  last_error: string | null;
  schedule: string;
}

interface HealthCheck {
  ready: boolean;
  shopee_configured: boolean;
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
}

interface FbGroup {
  group_id: string;
  name: string;
  url: string;
  category_name: string;
  members_count: number;
  status: 'DISCOVERED' | 'PENDING' | 'APPROVED' | 'REJECTED';
  last_posted_at: string | null;
}

interface SystemConfig {
  shopee_app_id: string;
  shopee_secret: string;
  shopee_cookie: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
  fb_account_cookie: string;
  fb_chrome_profile_path: string;
  min_rating_star: number;
  min_historical_sold: number;
  min_discount_percent: number;
  max_groups_per_day: number;
  top_deals_per_category: number;
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
  activeTab: 'dashboard' | 'deals' | 'groups' | 'settings' | 'schedule' | 'logs' = 'dashboard';

  stats: Stats = {
    categories_count: 0,
    deals_today: 0,
    deals_total: 0,
    groups_total: 0,
    groups_pending: 0,
    groups_approved: 0,
    groups_discovered: 0,
    last_run: null,
    is_running: false,
    last_error: null,
    schedule: '08:00 (Hàng ngày)'
  };

  health: HealthCheck = {
    ready: true,
    shopee_configured: false,
    telegram_configured: false,
    facebook_configured: false,
    issues: []
  };

  schedule: ScheduleConfig = {
    enabled: true,
    time: '08:00',
    cats: 3,
    next_run_display: '08:00 Hàng ngày'
  };

  config: SystemConfig = {
    shopee_app_id: '',
    shopee_secret: '',
    shopee_cookie: '',
    telegram_bot_token: '',
    telegram_chat_id: '',
    fb_account_cookie: '',
    fb_chrome_profile_path: '',
    min_rating_star: 4.6,
    min_historical_sold: 200,
    min_discount_percent: 15,
    max_groups_per_day: 3,
    top_deals_per_category: 3
  };

  deals: Deal[] = [];
  groups: FbGroup[] = [];
  logsContent = 'Đang tải nhật ký...';
  autoRefreshLogs = true;
  pollSub?: Subscription;

  toastMessage = '';
  toastType: 'success' | 'error' | 'info' = 'info';
  showToast = false;

  testingShopee = false;
  testingTelegram = false;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.fetchStats();
    this.fetchHealth();
    this.fetchSchedule();
    this.fetchConfig();
    this.fetchDeals();
    this.fetchGroups();
    this.fetchLogs();

    this.pollSub = interval(4000).subscribe(() => {
      this.fetchStats();
      this.fetchHealth();
      if (this.activeTab === 'logs' && this.autoRefreshLogs) {
        this.fetchLogs();
      }
    });
  }

  ngOnDestroy(): void {
    if (this.pollSub) {
      this.pollSub.unsubscribe();
    }
  }

  switchTab(tab: 'dashboard' | 'deals' | 'groups' | 'settings' | 'schedule' | 'logs'): void {
    this.activeTab = tab;
    if (tab === 'deals') this.fetchDeals();
    if (tab === 'groups') this.fetchGroups();
    if (tab === 'logs') this.fetchLogs();
    if (tab === 'settings') this.fetchConfig();
    if (tab === 'schedule') this.fetchSchedule();
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

  fetchDeals(): void {
    this.http.get<Deal[]>(`${this.apiUrl}/deals?limit=30`).subscribe({
      next: (res) => (this.deals = res),
      error: (err) => console.error(err)
    });
  }

  fetchGroups(): void {
    this.http.get<FbGroup[]>(`${this.apiUrl}/groups`).subscribe({
      next: (res) => (this.groups = res),
      error: (err) => console.error(err)
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

  triggerToast(msg: string, type: 'success' | 'error' | 'info' = 'info'): void {
    this.toastMessage = msg;
    this.toastType = type;
    this.showToast = true;
    setTimeout(() => {
      this.showToast = false;
    }, 5000);
  }
}
