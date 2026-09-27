import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <!-- Mobile Hamburger Toggle -->
    <div class="mobile-nav-bar">
      <div class="mobile-brand">
        <span class="brand-icon">⚡</span>
        <span class="brand-title">Auto-Aff Hub</span>
      </div>
      <button class="hamburger-btn" (click)="toggleMobileMenu()">
        {{ isMobileOpen ? '✕' : '☰' }}
      </button>
    </div>

    <!-- Backdrop for Mobile -->
    <div class="sidebar-backdrop" *ngIf="isMobileOpen" (click)="closeMobileMenu()"></div>

    <!-- Sidebar Container -->
    <aside class="sidebar" [class.mobile-open]="isMobileOpen">
      <div class="brand">
        <div class="brand-icon">⚡</div>
        <div class="brand-text">
          <h2>Shopee & Laz Aff</h2>
          <span>Multi-Platform Hub</span>
        </div>
      </div>

      <!-- Status Indicator -->
      <div class="status-box" [class.running]="stats?.is_running">
        <div class="status-dot"></div>
        <div class="status-info">
          <span class="status-label">Trạng thái hệ thống</span>
          <span class="status-value">{{ stats?.is_running ? 'Đang chạy quét deal...' : 'Sẵn sàng (Idle)' }}</span>
        </div>
      </div>

      <!-- Navigation Menu -->
      <nav class="nav-menu">
        <button class="nav-item" [class.active]="activeTab === 'dashboard'" (click)="onSelectTab('dashboard')">
          <span class="icon">📊</span>
          <span>Doanh Thu & ROI</span>
          <span class="badge badge-accent" *ngIf="(stats?.total_commission_vnd || 0) > 0">
            {{ stats.total_commission_vnd | number }}đ
          </span>
        </button>

        <button class="nav-item" [class.active]="activeTab === 'deals'" (click)="onSelectTab('deals')">
          <span class="icon">🛍️</span>
          <span>Săn Deal & Khuyến Mại</span>
          <span class="badge" *ngIf="stats?.deals_today > 0">{{ stats.deals_today }}</span>
        </button>

        <button class="nav-item" [class.active]="activeTab === 'marketing'" (click)="onSelectTab('marketing')">
          <span class="icon">📢</span>
          <span>Tiếp Thị & Lan Tỏa FB</span>
          <span class="badge badge-accent" *ngIf="stats?.groups_total > 0">{{ stats.groups_total }}</span>
        </button>

        <button class="nav-item" [class.active]="activeTab === 'settings'" (click)="onSelectTab('settings')">
          <span class="icon">⚙️</span>
          <span>Cài Đặt & Lịch Chạy</span>
          <span class="badge badge-accent">{{ schedule?.enabled ? schedule?.time : 'Tắt' }}</span>
        </button>

        <button class="nav-item" [class.active]="activeTab === 'logs'" (click)="onSelectTab('logs')">
          <span class="icon">📜</span>
          <span>Nhật Ký (Live Stream)</span>
        </button>
      </nav>

      <!-- Sidebar Footer -->
      <div class="sidebar-footer">
        <button class="btn-run" [disabled]="stats?.is_running" (click)="onRunWorkflow()">
          <span *ngIf="!stats?.is_running">▶ Kích Hoạt Chạy Ngay</span>
          <span *ngIf="stats?.is_running">⏳ Đang xử lý...</span>
        </button>
      </div>
    </aside>
  `,
  styles: [`
    .mobile-nav-bar {
      display: none;
      align-items: center;
      justify-content: space-between;
      padding: 12px 20px;
      background: rgba(15, 23, 42, 0.95);
      border-bottom: 1px solid rgba(56, 189, 248, 0.2);
      position: sticky;
      top: 0;
      z-index: 1000;
    }
    .mobile-brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      color: #fff;
    }
    .hamburger-btn {
      background: none;
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: #fff;
      font-size: 1.4rem;
      border-radius: 8px;
      padding: 4px 10px;
      cursor: pointer;
    }
    .sidebar-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.65);
      z-index: 998;
    }
    .sidebar {
      width: 280px;
      min-width: 280px;
      background: rgba(15, 23, 42, 0.85);
      border-right: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      flex-direction: column;
      height: 100vh;
      position: sticky;
      top: 0;
      backdrop-filter: blur(20px);
      z-index: 999;
      transition: transform 0.3s ease;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 24px 20px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .brand-icon {
      font-size: 1.8rem;
      background: linear-gradient(135deg, #f59e0b, #ef4444);
      border-radius: 12px;
      width: 44px;
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 14px rgba(245, 158, 11, 0.3);
    }
    .brand-text h2 {
      margin: 0;
      font-size: 1.1rem;
      font-weight: 700;
      color: #f8fafc;
      letter-spacing: -0.3px;
    }
    .brand-text span {
      font-size: 0.75rem;
      color: #94a3b8;
      font-weight: 500;
    }
    .status-box {
      margin: 16px;
      padding: 12px 14px;
      background: rgba(30, 41, 59, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 12px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .status-box.running {
      border-color: rgba(245, 158, 11, 0.4);
      background: rgba(245, 158, 11, 0.1);
    }
    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
      flex-shrink: 0;
    }
    .status-box.running .status-dot {
      background: #f59e0b;
      box-shadow: 0 0 8px #f59e0b;
      animation: pulse 1.5s infinite;
    }
    .status-info {
      display: flex;
      flex-direction: column;
    }
    .status-label {
      font-size: 0.7rem;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .status-value {
      font-size: 0.85rem;
      font-weight: 600;
      color: #e2e8f0;
    }
    .nav-menu {
      flex: 1;
      padding: 8px 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      overflow-y: auto;
    }
    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 14px;
      border-radius: 10px;
      color: #94a3b8;
      background: none;
      border: none;
      font-size: 0.9rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
      width: 100%;
      text-align: left;
    }
    .nav-item:hover {
      background: rgba(255, 255, 255, 0.05);
      color: #f1f5f9;
      transform: translateX(3px);
    }
    .nav-item.active {
      background: linear-gradient(90deg, rgba(56, 189, 248, 0.15), rgba(56, 189, 248, 0.05));
      color: #38bdf8;
      font-weight: 600;
      border-left: 3px solid #38bdf8;
    }
    .nav-item .icon {
      font-size: 1.15rem;
    }
    .badge {
      margin-left: auto;
      background: rgba(255, 255, 255, 0.1);
      color: #cbd5e1;
      padding: 2px 8px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .badge-accent {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
    }
    .sidebar-footer {
      padding: 16px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
    }
    .btn-run {
      width: 100%;
      padding: 12px 16px;
      border-radius: 12px;
      background: linear-gradient(135deg, #0ea5e9, #3b82f6);
      color: #fff;
      font-weight: 700;
      font-size: 0.92rem;
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(14, 165, 233, 0.4);
      transition: all 0.2s ease;
    }
    .btn-run:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(14, 165, 233, 0.55);
    }
    .btn-run:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(0.9); }
    }

    /* Responsive */
    @media (max-width: 992px) {
      .mobile-nav-bar {
        display: flex;
      }
      .sidebar-backdrop {
        display: block;
      }
      .sidebar {
        position: fixed;
        left: 0;
        top: 0;
        bottom: 0;
        transform: translateX(-100%);
        box-shadow: 10px 0 30px rgba(0,0,0,0.5);
      }
      .sidebar.mobile-open {
        transform: translateX(0);
      }
    }
  `]
})
export class SidebarComponent {
  @Input() activeTab: string = 'dashboard';
  @Input() stats: any = {};
  @Input() schedule: any = {};

  @Output() tabSelected = new EventEmitter<string>();
  @Output() runWorkflow = new EventEmitter<void>();

  isMobileOpen = false;

  toggleMobileMenu() {
    this.isMobileOpen = !this.isMobileOpen;
  }

  closeMobileMenu() {
    this.isMobileOpen = false;
  }

  onSelectTab(tab: string) {
    this.tabSelected.emit(tab);
    this.closeMobileMenu();
  }

  onRunWorkflow() {
    this.runWorkflow.emit();
    this.closeMobileMenu();
  }
}
