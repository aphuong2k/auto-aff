import { Component, OnInit, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../services/api.service';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-group-quality-widget',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="quality-widget glass-card">
      <div class="widget-header">
        <div class="widget-title">
          <span class="icon">🛡️</span>
          <div>
            <h3>Chất Lượng Nhóm & Tránh Group Ma</h3>
            <span class="sub-label">Đo lường tự động: tương tác thật, tỷ lệ duyệt bài & thời gian chờ</span>
          </div>
        </div>
        <div class="widget-actions">
          <button class="btn-action btn-check" [disabled]="checkingApprovals" (click)="checkApprovals()">
            <span *ngIf="!checkingApprovals">🔍 Check Duyệt Bài</span>
            <span *ngIf="checkingApprovals">⏳ Đang rà soát...</span>
          </button>
          <button class="btn-action btn-clean" [disabled]="cleaningGhosts" (click)="cleanupGhosts()">
            <span *ngIf="!cleaningGhosts">🧹 Dọn Dẹp Group Ma</span>
            <span *ngIf="cleaningGhosts">⏳ Đang dọn dẹp...</span>
          </button>
        </div>
      </div>

      <div class="metrics-grid">
        <div class="metric-card healthy">
          <div class="metric-badge">🟢 HEALTHY</div>
          <div class="metric-value">{{ metrics?.healthy_count || 0 }}</div>
          <div class="metric-desc">Nhóm tương tác sôi nổi (Điểm >= 60)</div>
        </div>

        <div class="metric-card warning">
          <div class="metric-badge">🟡 WARNING</div>
          <div class="metric-value">{{ metrics?.warning_count || 0 }}</div>
          <div class="metric-desc">Nhóm tương tác giảm (30 - 59)</div>
        </div>

        <div class="metric-card ghost">
          <div class="metric-badge">🔴 GHOST</div>
          <div class="metric-value">{{ metrics?.ghost_count || 0 }}</div>
          <div class="metric-desc">Nhóm ma / chết tương tác (&lt; 30)</div>
        </div>

        <div class="metric-card restricted">
          <div class="metric-badge">🚫 BỊ HẠN CHẾ</div>
          <div class="metric-value">{{ metrics?.restricted_count || 0 }}</div>
          <div class="metric-desc">Bị chờ duyệt/từ chối &gt;= 2 lần (Auto-Out)</div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .quality-widget {
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 16px;
      padding: 20px 24px;
      margin-bottom: 24px;
      backdrop-filter: blur(12px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    }
    .widget-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      flex-wrap: wrap;
      gap: 12px;
    }
    .widget-title {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .widget-title .icon {
      font-size: 1.8rem;
    }
    .widget-title h3 {
      margin: 0;
      font-size: 1.15rem;
      font-weight: 700;
      color: #f1f5f9;
    }
    .sub-label {
      font-size: 0.8rem;
      color: #94a3b8;
    }
    .widget-actions {
      display: flex;
      gap: 10px;
    }
    .btn-action {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s ease;
    }
    .btn-check {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.35);
    }
    .btn-check:hover:not(:disabled) {
      background: rgba(56, 189, 248, 0.25);
      transform: translateY(-1px);
    }
    .btn-clean {
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.35);
    }
    .btn-clean:hover:not(:disabled) {
      background: rgba(239, 68, 68, 0.25);
      transform: translateY(-1px);
    }
    .btn-action:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 14px;
    }
    .metric-card {
      background: rgba(30, 41, 59, 0.6);
      border-radius: 12px;
      padding: 14px 16px;
      border-left: 4px solid #64748b;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .metric-card.healthy {
      border-left-color: #10b981;
    }
    .metric-card.warning {
      border-left-color: #f59e0b;
    }
    .metric-card.ghost {
      border-left-color: #ef4444;
    }
    .metric-card.restricted {
      border-left-color: #a855f7;
    }
    .metric-badge {
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #cbd5e1;
    }
    .metric-value {
      font-size: 1.8rem;
      font-weight: 800;
      color: #fff;
      line-height: 1.1;
    }
    .metric-desc {
      font-size: 0.75rem;
      color: #94a3b8;
    }
  `]
})
export class GroupQualityWidgetComponent implements OnInit {
  metrics: any = null;
  cleaningGhosts = false;
  checkingApprovals = false;

  @Output() refreshRequested = new EventEmitter<void>();

  constructor(
    private api: ApiService,
    private toast: ToastService
  ) {}

  ngOnInit() {
    this.fetchMetrics();
  }

  fetchMetrics() {
    this.api.getGroupQualityMetrics().subscribe({
      next: (res) => {
        this.metrics = res;
      },
      error: () => {}
    });
  }

  checkApprovals() {
    this.checkingApprovals = true;
    this.api.checkPendingApprovals().subscribe({
      next: (res) => {
        this.checkingApprovals = false;
        this.toast.info('Đã khởi chạy tiến trình quét duyệt bài trong nền.');
        this.fetchMetrics();
        this.refreshRequested.emit();
      },
      error: (err) => {
        this.checkingApprovals = false;
        this.toast.error('Lỗi khi kích hoạt kiểm tra duyệt bài: ' + (err.error?.detail || err.message));
      }
    });
  }

  cleanupGhosts() {
    if (!confirm('Bạn có chắc muốn tự động rời khỏi tất cả các nhóm có điểm sức khỏe < 30 (Group Ma)?')) {
      return;
    }
    this.cleaningGhosts = true;
    this.api.cleanupGhostGroups(30).subscribe({
      next: (res) => {
        this.cleaningGhosts = false;
        this.toast.success(res.message || 'Đã dọn dẹp các nhóm ma thành công!');
        this.fetchMetrics();
        this.refreshRequested.emit();
      },
      error: (err) => {
        this.cleaningGhosts = false;
        this.toast.error('Lỗi dọn dẹp nhóm ma: ' + (err.error?.detail || err.message));
      }
    });
  }
}
