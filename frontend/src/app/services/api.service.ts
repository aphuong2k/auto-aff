import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Tự động nhận diện URL: Dùng relative path '/api' khi chạy qua proxy / production
  // Hoặc fallback tới 'http://localhost:8000/api' nếu chạy trực tiếp
  public baseUrl: string = '/api';

  constructor(private http: HttpClient) {
    if (typeof window !== 'undefined') {
      const port = window.location.port;
      // Nếu chạy port dev server 4200 mà không cấu hình proxy, có thể fallback
      if (port === '4200' && window.location.hostname === 'localhost') {
        this.baseUrl = '/api';
      }
    }
  }

  // --- STATS & HEALTH ---
  getStats(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/stats`);
  }

  getHealth(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/health`);
  }

  getSchedule(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/schedule`);
  }

  saveSchedule(schedule: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/schedule`, schedule);
  }

  // --- DEALS & CATEGORIES ---
  getDeals(category?: string, platform?: string): Observable<any[]> {
    let params = new HttpParams();
    if (category && category !== 'ALL') params = params.set('category', category);
    if (platform && platform !== 'ALL') params = params.set('platform', platform);
    return this.http.get<any[]>(`${this.baseUrl}/deals`, { params });
  }

  getDealsInventory(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/deals/inventory`);
  }

  getDealImageUrl(itemId: string): string {
    return `${this.baseUrl}/deals/image/${itemId}`;
  }

  getCategories(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/categories`);
  }

  saveCategory(category: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/categories`, category);
  }

  deleteCategory(catId: number): Observable<any> {
    return this.http.delete<any>(`${this.baseUrl}/categories/${catId}`);
  }

  // --- FACEBOOK GROUPS & HEALTH QUALITY ---
  getFbGroups(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/groups`);
  }

  addFbGroup(group: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups`, group);
  }

  deleteFbGroup(id: number | string): Observable<any> {
    return this.http.delete<any>(`${this.baseUrl}/groups/${id}`);
  }

  leaveFbGroup(groupUrl: string, accountId?: number | string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/leave`, { group_url: groupUrl, account_id: accountId });
  }

  checkGroupHealth(groupUrl: string, accountId?: number | string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/check-health`, { group_url: groupUrl, account_id: accountId });
  }

  checkPendingJoin(groupUrl: string, accountId?: number | string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/check-pending`, { group_url: groupUrl, account_id: accountId });
  }

  checkPendingApprovals(accountId?: number | string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/posts/check-approvals`, { account_id: accountId });
  }

  syncJoinedGroups(accountId?: number | string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/sync-joined`, { account_id: accountId });
  }

  auditAndCleanGroups(liveScan: boolean = true, maxLiveScan: number = 5, accountId?: number | string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/audit-and-clean`, { live_scan: liveScan, max_live_scan: maxLiveScan, account_id: accountId });
  }

  discoverFbGroups(categoryName: string = 'Săn Deal Tổng Hợp', maxGroups: number = 5, accountId?: number | string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/discover`, { category_name: categoryName, max_groups: maxGroups, account_id: accountId });
  }

  getGroupQualityMetrics(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/groups/quality-metrics`);
  }

  cleanupGhostGroups(maxScore: number = 30): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/cleanup-ghosts`, { max_score: maxScore });
  }

  // --- CLOSED-LOOP WORKFLOW ---
  getClosedLoopStatus(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/workflow/closed-loop/status`);
  }

  triggerClosedLoopCycle(): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/workflow/closed-loop/run`, {});
  }

  triggerClosedLoopStep(): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/workflow/closed-loop/step`, {});
  }

  getClosedLoopHistory(limit: number = 30): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/workflow/closed-loop/history?limit=${limit}`);
  }

  getWorkloadAccounts(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/accounts/workload`);
  }

  // --- OUTREACH & POSTING ---
  postToSingleGroup(payload: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/post-single`, payload);
  }

  getGradualPostingStatus(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/groups/gradual-posting-status`);
  }

  startGradualPosting(payload: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/start-gradual-posting`, payload);
  }

  stopGradualPosting(): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/groups/stop-gradual-posting`, {});
  }

  getSeedingHistory(limit: number = 50): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/outreach/seeding-history?limit=${limit}`);
  }

  getPostedLogs(limit: number = 50, postType?: string): Observable<any[]> {
    let url = `${this.baseUrl}/outreach/posted-logs?limit=${limit}`;
    if (postType) url += `&type=${postType}`;
    return this.http.get<any[]>(url);
  }

  deletePostedLog(id: number): Observable<any> {
    return this.http.delete<any>(`${this.baseUrl}/outreach/posted-logs/${id}`);
  }

  // --- PROMOTIONS & VOUCHERS ---
  getVouchers(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/promotions/voucher-codes`);
  }

  saveVoucher(voucher: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/promotions/voucher-codes`, voucher);
  }

  deleteVoucher(code: string): Observable<any> {
    return this.http.delete<any>(`${this.baseUrl}/promotions/voucher-codes/${code}`);
  }

  getPromotions(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/promotions`);
  }

  generatePromoPosts(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/promotions/generated-posts`);
  }

  // --- CONFIG & SYSTEM ---
  getConfig(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/config`);
  }

  saveConfig(config: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/config`, config);
  }

  getLearnedKeywords(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/keywords/learned`);
  }

  deleteLearnedKeyword(id: number): Observable<any> {
    return this.http.delete<any>(`${this.baseUrl}/keywords/learned/${id}`);
  }

  getSystemLogs(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/logs`);
  }

  clearSystemLogs(): Observable<any> {
    return this.http.delete<any>(`${this.baseUrl}/logs`);
  }

  runWorkflowNow(payload?: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/workflow/run`, payload || {});
  }

  resetAllData(): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/reset-data`, {});
  }
}
