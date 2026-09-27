import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration: number;
}

@Injectable({
  providedIn: 'root'
})
export class ToastService {
  private toastsSubject = new BehaviorSubject<ToastMessage[]>([]);
  public toasts$: Observable<ToastMessage[]> = this.toastsSubject.asObservable();

  show(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info', duration: number = 3500) {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: ToastMessage = { id, type, message, duration };
    const current = this.toastsSubject.getValue();
    this.toastsSubject.next([...current, newToast]);

    if (duration > 0) {
      setTimeout(() => {
        this.remove(id);
      }, duration);
    }
  }

  success(message: string, duration: number = 3500) {
    this.show(message, 'success', duration);
  }

  error(message: string, duration: number = 5000) {
    this.show(message, 'error', duration);
  }

  warning(message: string, duration: number = 4000) {
    this.show(message, 'warning', duration);
  }

  info(message: string, duration: number = 3000) {
    this.show(message, 'info', duration);
  }

  remove(id: string) {
    const current = this.toastsSubject.getValue();
    this.toastsSubject.next(current.filter(t => t.id !== id));
  }

  clear() {
    this.toastsSubject.next([]);
  }
}
