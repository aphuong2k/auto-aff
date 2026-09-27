import { Injectable, OnDestroy } from '@angular/core';
import { Subject, Subscription, timer } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class PollingService implements OnDestroy {
  private isRunning = false;
  private activeTab = 'dashboard';
  private paused = false;
  private pollTrigger = new Subject<string>();
  public pollTrigger$ = this.pollTrigger.asObservable();
  private sub?: Subscription;

  constructor() {
    this.startAdaptiveTimer();
  }

  setSystemRunning(running: boolean) {
    if (this.isRunning !== running) {
      this.isRunning = running;
      this.startAdaptiveTimer();
    }
  }

  setActiveTab(tab: string) {
    this.activeTab = tab;
    this.triggerNow();
  }

  getActiveTab(): string {
    return this.activeTab;
  }

  pause() {
    this.paused = true;
  }

  resume() {
    this.paused = false;
    this.triggerNow();
  }

  triggerNow() {
    if (!this.paused) {
      this.pollTrigger.next(this.activeTab);
    }
  }

  private startAdaptiveTimer() {
    if (this.sub) {
      this.sub.unsubscribe();
    }
    // 3s khi hệ thống đang chạy workflow, 15s khi ở trạng thái nghỉ (Idle)
    const intervalMs = this.isRunning ? 3000 : 15000;
    this.sub = timer(intervalMs, intervalMs).subscribe(() => {
      if (!this.paused) {
        this.pollTrigger.next(this.activeTab);
      }
    });
  }

  ngOnDestroy() {
    if (this.sub) {
      this.sub.unsubscribe();
    }
  }
}
