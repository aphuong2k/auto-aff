import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToastService, ToastMessage } from '../../services/toast.service';

@Component({
  selector: 'app-toast',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="toast-container" *ngIf="(toastService.toasts$ | async) as toasts">
      <div
        *ngFor="let t of toasts"
        class="toast-item"
        [ngClass]="'toast-' + t.type"
        (click)="toastService.remove(t.id)"
      >
        <span class="toast-icon">
          <span *ngIf="t.type === 'success'">✅</span>
          <span *ngIf="t.type === 'error'">❌</span>
          <span *ngIf="t.type === 'warning'">⚠️</span>
          <span *ngIf="t.type === 'info'">ℹ️</span>
        </span>
        <span class="toast-message">{{ t.message }}</span>
        <button class="toast-close" (click)="toastService.remove(t.id); $event.stopPropagation()">×</button>
      </div>
    </div>
  `,
  styles: [`
    .toast-container {
      position: fixed;
      top: 24px;
      right: 24px;
      z-index: 99999;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: 420px;
      pointer-events: none;
    }
    .toast-item {
      pointer-events: auto;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 18px;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(16px);
      font-size: 0.9rem;
      font-weight: 500;
      color: #fff;
      cursor: pointer;
      animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      transition: transform 0.2s ease, opacity 0.2s ease;
    }
    .toast-item:hover {
      transform: translateY(-2px);
    }
    .toast-success {
      background: rgba(16, 185, 129, 0.9);
      border: 1px solid rgba(52, 211, 153, 0.4);
    }
    .toast-error {
      background: rgba(239, 68, 68, 0.9);
      border: 1px solid rgba(248, 113, 113, 0.4);
    }
    .toast-warning {
      background: rgba(245, 158, 11, 0.9);
      border: 1px solid rgba(251, 191, 36, 0.4);
    }
    .toast-info {
      background: rgba(14, 165, 233, 0.9);
      border: 1px solid rgba(56, 189, 248, 0.4);
    }
    .toast-icon {
      font-size: 1.1rem;
      flex-shrink: 0;
    }
    .toast-message {
      flex: 1;
      line-height: 1.4;
    }
    .toast-close {
      background: none;
      border: none;
      color: rgba(255, 255, 255, 0.7);
      font-size: 1.3rem;
      cursor: pointer;
      padding: 0 4px;
      line-height: 1;
    }
    .toast-close:hover {
      color: #fff;
    }
    @keyframes slideIn {
      from {
        transform: translateX(60px);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
  `]
})
export class ToastComponent {
  constructor(public toastService: ToastService) {}
}
