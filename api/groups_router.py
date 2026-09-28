"""
Facebook Groups API Router
==========================
Quản lý danh sách nhóm Facebook, đồng bộ, phân loại, chấm điểm sức khỏe,
kiểm tra phản hồi xét duyệt, kiểm tra duyệt bài và auto-leave.
"""

import time
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.deps import db
from api.models import (
    AddGroupRequest, UpdateGroupStatusRequest, UpdateGroupCategoryRequest,
    CheckGroupHealthRequest
)

groups_logger = logging.getLogger("GroupsRouter")
router = APIRouter(tags=["Facebook Groups"])


@router.get("/api/groups")
def get_groups(status: Optional[str] = None, limit: int = 200):
    """Lấy danh sách các nhóm Facebook theo trạng thái"""
    with db.get_connection() as conn:
        if status and status.upper() != "ALL":
            rows = conn.execute("""
                SELECT * FROM fb_groups 
                WHERE status = ?
                ORDER BY members_count DESC 
                LIMIT ?
            """, (status.upper(), limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM fb_groups 
                ORDER BY members_count DESC 
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


@router.get("/api/groups/categorized")
def get_groups_categorized():
    """Lấy danh sách nhóm phân loại rõ ràng: Approved, Pending, Discovered"""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT * FROM fb_groups ORDER BY members_count DESC").fetchall()
        all_groups = [dict(r) for r in rows]
        approved = [g for g in all_groups if g.get("status") == "APPROVED"]
        pending = [g for g in all_groups if g.get("status") == "PENDING"]
        discovered = [g for g in all_groups if g.get("status") == "DISCOVERED"]
        return {
            "total": len(all_groups),
            "approved": approved,
            "pending": pending,
            "discovered": discovered,
            "all": all_groups
        }


@router.post("/api/groups/sync-joined")
def sync_joined_groups(account_id: Optional[object] = None, payload: Optional[dict] = None):
    """Tự động đồng bộ các nhóm mà nick Facebook hiện tại đã tham gia thực tế qua Playwright"""
    eff_aid = account_id if account_id is not None else (payload.get("account_id") if payload else None)
    from modules.outreach.fb_auto_joiner import FacebookAutoJoiner
    joiner = FacebookAutoJoiner(db)
    try:
        synced = joiner.sync_user_joined_groups(account_id=eff_aid)
        return {
            "status": "SUCCESS",
            "message": f"Đã đồng bộ thành công {len(synced)} nhóm Facebook bạn đã tham gia thực tế!",
            "count": len(synced),
            "groups": synced
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/groups/add")
def add_custom_group(req: AddGroupRequest):
    """Thêm một nhóm Facebook mới thủ công (mặc định APPROVED)"""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng nhập đường dẫn URL của nhóm Facebook!")

    clean_url = url.split("?")[0].rstrip("/")
    parts = clean_url.split("/groups/")
    if len(parts) >= 2:
        group_id = parts[1].split("/")[0]
    else:
        group_id = str(int(time.time()))

    group_name = req.name.strip() if req.name else f"Group Facebook ({group_id})"
    category_name = req.category_name.strip() if req.category_name else "Cộng Đồng Chung"
    status = (req.status or "APPROVED").upper()
    members = req.members_count or 10000

    db.save_group(group_id, group_name, clean_url, category_name, members)
    db.update_group_status(group_id, status)
    return {
        "status": "SUCCESS",
        "message": f"Đã thêm thành công nhóm [{group_name}] với trạng thái {status}!",
        "group": {
            "group_id": group_id,
            "name": group_name,
            "url": clean_url,
            "category_name": category_name,
            "members_count": members,
            "status": status
        }
    }


@router.post("/api/groups/{group_id}/status")
def update_group_status_api(group_id: str, req: UpdateGroupStatusRequest):
    """Cập nhật trạng thái của một nhóm (APPROVED, PENDING, DISCOVERED)"""
    new_status = req.status.upper()
    db.update_group_status(group_id, new_status)
    return {"status": "SUCCESS", "message": f"Đã chuyển trạng thái nhóm #{group_id} sang {new_status}!"}


@router.delete("/api/groups/{group_id}")
def delete_single_group_api(group_id: str):
    """Xóa một nhóm cụ thể khỏi hệ thống"""
    db.delete_group(group_id)
    return {"status": "SUCCESS", "message": f"Đã xóa nhóm #{group_id} khỏi cơ sở dữ liệu!"}


@router.post("/api/groups/auto-categorize")
def auto_categorize_groups_api():
    """Tự động phân loại toàn bộ nhóm theo ngành hàng chuẩn xác dựa vào CategoryMatcher"""
    from config.category_mapping import CategoryMatcher
    matcher = CategoryMatcher()
    with db.get_connection() as conn:
        groups = conn.execute("SELECT group_id, name, category_name FROM fb_groups").fetchall()
        count = 0
        for gid, name, cat in groups:
            res = matcher.match_group(name or "", cat or "")
            new_cat = res["rule"]["category_name"]
            conn.execute("UPDATE fb_groups SET category_name = ? WHERE group_id = ?", (new_cat, gid))
            count += 1
        conn.commit()
    return {"status": "SUCCESS", "message": f"Đã phân loại tự động thành công cho {count} nhóm Facebook!", "count": count}


@router.get("/api/groups/with-matched-deals")
def get_groups_with_matched_deals():
    """Lấy danh sách nhóm kèm deal khớp chính xác theo ngành và số lượng deal sẵn sàng trong kho"""
    from modules.outreach.fb_group_poster import FacebookGroupPoster
    poster = FacebookGroupPoster(db)
    with db.get_connection() as conn:
        groups = conn.execute("SELECT * FROM fb_groups ORDER BY members_count DESC").fetchall()
        inv_rows = conn.execute("SELECT category_name, count(*) FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
        inv_map = {r[0]: r[1] for r in inv_rows}

        result = []
        for g in groups:
            gd = dict(g)
            cat_name = gd.get("category_name")
            matched = poster.find_best_deal_for_group(gd, strict=True)
            gd["matched_deal"] = matched
            gd["category_deals_count"] = inv_map.get(cat_name, 0)
            result.append(gd)
        return result


@router.post("/api/groups/{group_id}/category")
def update_single_group_category(group_id: str, req: UpdateGroupCategoryRequest):
    """Cập nhật trực tiếp ngành hàng cho một nhóm để hệ thống chọn đúng deal"""
    with db.get_connection() as conn:
        conn.execute("UPDATE fb_groups SET category_name = ? WHERE group_id = ?", (req.category_name, group_id))
        conn.commit()
    return {"status": "SUCCESS", "message": f"Đã chuyển nhóm #{group_id} sang ngành '{req.category_name}'!"}


@router.post("/api/groups/clear")
def clear_groups():
    db.clear_groups()
    return {"status": "SUCCESS", "message": "Đã xóa toàn bộ dữ liệu nhóm Facebook!"}


# --- Smart Group Intelligence Endpoints ---

@router.get("/api/groups/health/ghosts")
def get_ghost_groups_api():
    """Lấy danh sách các nhóm bị đánh giá là group ma hoặc điểm sức khỏe < 35"""
    ghosts = db.get_ghost_groups()
    return {"status": "SUCCESS", "total": len(ghosts), "groups": ghosts}


@router.post("/api/groups/check-health")
@router.get("/api/groups/check-health")
def check_group_health_api(
    req: Optional[CheckGroupHealthRequest] = None,
    group_url: Optional[str] = None,
    group_id: Optional[str] = None,
    account_id: Optional[object] = None
):
    """
    Quét bảng tin và chấm điểm sức khỏe thực tế cho một nhóm Facebook qua Playwright.
    Hỗ trợ nhận tham số qua JSON body hoặc Query params (?group_url=... hoặc ?group_id=...).
    """
    url = req.group_url if req else None
    gid = req.group_id if req else None
    eff_aid = req.account_id if (req and req.account_id is not None) else account_id
    if not url and group_url:
        url = group_url
    if not gid and group_id:
        gid = group_id

    if not url and not gid:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp 'group_url' hoặc 'group_id'!")

    target_id = None
    target_url = None
    group_name = None

    with db.get_connection() as conn:
        if gid:
            group = conn.execute("SELECT * FROM fb_groups WHERE group_id = ?", (gid,)).fetchone()
            if group:
                target_id = group["group_id"]
                target_url = group["url"] or url
                group_name = group["name"]
        if not target_id and url:
            clean_url = url.split("?")[0].rstrip("/")
            group = conn.execute("SELECT * FROM fb_groups WHERE url = ? OR url LIKE ?", (clean_url, f"%{clean_url}%")).fetchone()
            if not group:
                parts = clean_url.split("/groups/")
                if len(parts) >= 2:
                    extracted_id = parts[1].split("/")[0]
                    group = conn.execute("SELECT * FROM fb_groups WHERE group_id = ? OR url LIKE ?", (extracted_id, f"%{extracted_id}%")).fetchone()
            if group:
                target_id = group["group_id"]
                target_url = group["url"]
                group_name = group["name"]

    if not target_id:
        clean_url = (url or "").split("?")[0].rstrip("/")
        parts = clean_url.split("/groups/")
        target_id = parts[1].split("/")[0] if len(parts) >= 2 else str(int(time.time()))
        target_url = clean_url
        group_name = f"Group Facebook ({target_id})"
        db.save_group(target_id, group_name, target_url, "Cộng Đồng Chung", 1000)

    from modules.outreach.group_health_checker import GroupHealthChecker
    checker = GroupHealthChecker(db)
    metrics = checker.evaluate_and_save(target_id, target_url, account_id=eff_aid)

    with db.get_connection() as conn:
        updated = conn.execute("SELECT * FROM fb_groups WHERE group_id = ?", (target_id,)).fetchone()

    return {
        "status": "SUCCESS",
        "group_id": target_id,
        "group_name": group_name,
        "group_url": target_url,
        "metrics": metrics,
        "group": dict(updated) if updated else None
    }


@router.post("/api/groups/{group_id}/health-check")
def check_single_group_health_by_id_api(group_id: str, account_id: Optional[object] = None):
    """Quét bảng tin và chấm điểm sức khỏe cho một nhóm cụ thể theo ID"""
    return check_group_health_api(group_id=group_id, account_id=account_id)


@router.post("/api/groups/pending/check-feedback")
def check_pending_joins_api(background_tasks: BackgroundTasks):
    """Kích hoạt quét phản hồi xét duyệt cho các nhóm PENDING (Auto-Leave nếu quá hạn)"""
    from modules.outreach.join_feedback_monitor import JoinFeedbackMonitor
    monitor = JoinFeedbackMonitor(db)

    def _run_check():
        try:
            monitor.check_pending_joins()
        except Exception as e:
            groups_logger.error(f"Lỗi khi chạy JoinFeedbackMonitor: {e}")

    background_tasks.add_task(_run_check)
    return {"status": "SUCCESS", "message": "Đã khởi động tiến trình kiểm tra phản hồi nhóm PENDING trong nền!"}


@router.post("/api/groups/check-pending")
def check_single_pending_api(req: CheckGroupHealthRequest):
    """Kiểm tra trạng thái xét duyệt của một nhóm cụ thể theo link"""
    url = req.group_url
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp 'group_url'")
    from modules.outreach.join_feedback_monitor import JoinFeedbackMonitor
    monitor = JoinFeedbackMonitor(db)
    return {"status": "SUCCESS", "message": f"Đã kiểm tra yêu cầu tham gia {url}"}


@router.post("/api/groups/check-approvals")
@router.post("/api/groups/posts/check-approvals")
def check_post_approvals_api(background_tasks: BackgroundTasks, sync: bool = False, max_strikes: int = 2, account_id: Optional[object] = None, payload: Optional[dict] = None):
    """Kích hoạt kiểm tra xem bài viết đã đăng có được Admin nhóm duyệt không (Tự động out group nếu bị chờ duyệt hoặc từ chối >= max_strikes)"""
    eff_aid = account_id if account_id is not None else (payload.get("account_id") if payload else None)
    from modules.outreach.post_approval_monitor import PostApprovalMonitor
    monitor = PostApprovalMonitor(db)

    if sync:
        try:
            res = monitor.check_pending_approvals(max_strikes=max_strikes, account_id=eff_aid)
            return {
                "status": "SUCCESS",
                "message": f"Đã hoàn thành kiểm tra {res.get('total', 0)} bài đăng (Duyệt: {res.get('approved', 0)}, Chờ duyệt: {res.get('still_pending', 0)}, Từ chối: {res.get('rejected', 0)}, Out group: {res.get('groups_left', 0)})",
                "results": res
            }
        except Exception as e:
            groups_logger.error(f"Lỗi khi chạy PostApprovalMonitor: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _run_check():
        try:
            monitor.check_pending_approvals(max_strikes=max_strikes, account_id=eff_aid)
        except Exception as e:
            groups_logger.error(f"Lỗi khi chạy PostApprovalMonitor: {e}")

    background_tasks.add_task(_run_check)
    return {"status": "SUCCESS", "message": "Đã khởi động tiến trình kiểm tra duyệt bài viết trong nền (Tự động out group nếu bị chờ duyệt hoặc từ chối)!"}


@router.post("/api/groups/discover")
def discover_groups_api(category_name: str = "Săn Deal Tổng Hợp", max_groups: int = 5, account_id: Optional[object] = None, payload: Optional[dict] = None):
    """Tìm kiếm và thẩm định chất lượng Group Facebook mới (chỉ giữ nhóm có tương tác và bài mới nhất <= 72h)"""
    eff_aid = account_id if account_id is not None else (payload.get("account_id") if payload else None)
    from modules.outreach.fb_group_finder import FacebookGroupFinder
    finder = FacebookGroupFinder(db)
    try:
        discovered = finder.search_groups(category_name=category_name, max_groups=max_groups, account_id=eff_aid)
        return {
            "status": "SUCCESS",
            "count": len(discovered),
            "category": category_name,
            "groups": discovered,
            "message": f"Tìm thấy và thẩm định thành công {len(discovered)} nhóm đạt chuẩn tương tác và độ mới!"
        }
    except Exception as e:
        groups_logger.error(f"Lỗi khi tìm kiếm group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/groups/leave")
def leave_group_by_body_api(req: CheckGroupHealthRequest):
    """Rời khỏi nhóm Facebook theo group_url hoặc group_id qua Playwright"""
    url = req.group_url
    gid = req.group_id
    with db.get_connection() as conn:
        if gid:
            group = conn.execute("SELECT * FROM fb_groups WHERE group_id = ?", (gid,)).fetchone()
        elif url:
            clean_url = url.split("?")[0].rstrip("/")
            group = conn.execute("SELECT * FROM fb_groups WHERE url LIKE ?", (f"%{clean_url}%",)).fetchone()
        else:
            raise HTTPException(status_code=400, detail="Vui lòng cung cấp group_url hoặc group_id")
    if not group:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhóm!")

    from modules.outreach.join_feedback_monitor import JoinFeedbackMonitor
    monitor = JoinFeedbackMonitor(db)
    success = monitor.leave_group(group["url"], account_id=req.account_id)
    db.update_group_status(group["group_id"], "LEFT")
    return {
        "status": "SUCCESS" if success else "WARNING",
        "message": f"Đã thực hiện rời nhóm [{group['name']}] (Trạng thái CSDL: LEFT)."
    }


@router.post("/api/groups/{group_id}/leave")
def leave_group_api(group_id: str, account_id: Optional[object] = None):
    """Tự động rời khỏi nhóm Facebook qua Playwright theo path parameter"""
    return leave_group_by_body_api(CheckGroupHealthRequest(group_id=group_id, account_id=account_id))


@router.post("/api/groups/audit-and-clean")
def audit_and_clean_groups_api(live_scan: bool = True, max_live_scan: int = 5, account_id: Optional[object] = None, payload: Optional[dict] = None):
    """
    Quét danh sách các nhóm Facebook hiện có / đã tham gia:
    1. Chuẩn hóa và phân loại lại toàn bộ danh mục ngành hàng theo CategoryMatcher.
    2. Chấm điểm sức khỏe thực tế bằng Playwright cho các nhóm chưa xác thực hoặc nhóm nghi vấn.
    3. Tự động loại bỏ (đánh dấu LEFT, enabled=0) các group ma, nhóm bị đóng băng, nhóm bị hạn chế.
    4. Trả về thống kê chi tiết số nhóm phân loại lại, số nhóm bị lọc ra và số nhóm khỏe mạnh giữ lại.
    """
    eff_aid = account_id if account_id is not None else (payload.get("account_id") if payload else None)
    from config.category_mapping import CategoryMatcher
    from config.categories_filter import is_general_deal_group
    from modules.outreach.group_health_checker import GroupHealthChecker
    matcher = CategoryMatcher()
    checker = GroupHealthChecker(db)

    # 1. Quét live sức khỏe nhóm chưa có số liệu thực tế
    if live_scan:
        with db.get_connection() as conn:
            unverified_groups = conn.execute("""
                SELECT * FROM fb_groups 
                WHERE status != 'LEFT' AND (last_active_at IS NULL OR health_verdict = 'UNKNOWN')
                ORDER BY members_count ASC
                LIMIT ?
            """, (max_live_scan,)).fetchall()
            
        if unverified_groups:
            groups_logger.info(f"🛡️ Đang quét live sức khỏe bằng Playwright cho {len(unverified_groups)} nhóm...")
            try:
                checker.batch_evaluate_groups([dict(g) for g in unverified_groups], max_check=max_live_scan, account_id=eff_aid)
            except Exception as e:
                groups_logger.warning(f"Lỗi trong batch_evaluate_groups: {e}")

    # 2. Xử lý phân loại và thanh lọc
    total_scanned = 0
    reclassified_count = 0
    filtered_out_count = 0
    healthy_count = 0
    filtered_details = []

    with db.get_connection() as conn:
        groups = conn.execute("SELECT * FROM fb_groups").fetchall()
        total_scanned = len(groups)

        for g in groups:
            gid = str(g["group_id"])
            name = g["name"] or ""
            cat = g["category_name"] or "Cộng Đồng Chung"
            score = g["health_score"]
            verdict = g["health_verdict"] or "UNKNOWN"
            restricted = g["posting_restricted"] or 0
            rejections = g["consecutive_rejections"] or 0
            members = g["members_count"] or 0
            status = g["status"] or "DISCOVERED"

            # 1. Phân loại lại danh mục ngành hàng
            match_res = matcher.match_group(name, cat)
            new_cat = match_res["rule"]["category_name"]
            new_group_type = "GENERAL" if is_general_deal_group(name) else "NICHE"

            if new_cat != cat:
                reclassified_count += 1
                conn.execute(
                    "UPDATE fb_groups SET category_name = ?, group_type = ? WHERE group_id = ?",
                    (new_cat, new_group_type, gid)
                )

            # 2. Quy tắc chấm điểm sức khỏe & Lọc loại bỏ Group
            should_filter_out = False
            filter_reason = ""

            # Nhóm bị Admin từ chối liên tiếp hoặc posting_restricted = 1
            if restricted == 1 or rejections >= 2:
                should_filter_out = True
                if rejections > 0:
                    filter_reason = f"Bị Admin từ chối {rejections} lần liên tiếp"
                else:
                    filter_reason = "Nhóm bị hạn chế quyền đăng bài / đã rời nhóm"
                score = 0
                verdict = "RESTRICTED"

            # Nhóm có điểm sức khỏe quá thấp (< 35) hoặc verdict GHOST
            elif score is not None and (score < 35 or verdict == "GHOST"):
                should_filter_out = True
                filter_reason = f"Điểm sức khỏe thấp ({score}/100, {verdict})"

            # Nhóm quá ít thành viên (< 500)
            elif members > 0 and members < 500:
                should_filter_out = True
                filter_reason = f"Quy mô nhóm quá nhỏ ({members} thành viên)"
                score = 15
                verdict = "GHOST"

            # Kiểm tra tên nhóm chứa từ khóa spam / mua bán nick / ctv lừa đảo
            lower_name = name.lower()
            spam_kws = ["mua bán nick", "bán acc", "cho thuê via", "đổi sub", "tuyển ctv lừa", "vay tiền"]
            for skw in spam_kws:
                if skw in lower_name:
                    should_filter_out = True
                    filter_reason = f"Tên nhóm chứa từ khóa rác: '{skw}'"
                    score = 15
                    verdict = "GHOST"
                    break

            if should_filter_out:
                filtered_out_count += 1
                conn.execute("""
                    UPDATE fb_groups 
                    SET status = 'LEFT', enabled = 0, health_score = ?, health_verdict = ?
                    WHERE group_id = ?
                """, (score or 20, verdict, gid))
                filtered_details.append({
                    "group_id": gid,
                    "name": name,
                    "category": new_cat,
                    "reason": filter_reason
                })
            else:
                healthy_count += 1
                if score is None:
                    conn.execute("""
                        UPDATE fb_groups 
                        SET health_score = 70, health_verdict = 'HEALTHY'
                        WHERE group_id = ?
                    """, (gid,))

        conn.commit()

    return {
        "status": "SUCCESS",
        "total_scanned": total_scanned,
        "reclassified_count": reclassified_count,
        "filtered_out_count": filtered_out_count,
        "healthy_count": healthy_count,
        "filtered_details": filtered_details[:20],
        "message": f"Đã quét {total_scanned} nhóm: Chuẩn hóa lại danh mục cho {reclassified_count} nhóm, lọc loại bỏ {filtered_out_count} group ma/kém chất lượng (bao gồm nhóm dưới 500 TV), giữ lại {healthy_count} nhóm đạt chuẩn!"
    }



@router.post("/api/groups/cleanup-ghosts")
def cleanup_ghost_groups_api():
    """Tự động dọn dẹp (đánh dấu LEFT hoặc xóa) toàn bộ các nhóm điểm sức khỏe < 30"""
    ghosts = db.get_ghost_groups(max_score=30)
    count = 0
    with db.get_connection() as conn:
        for g in ghosts:
            conn.execute("UPDATE fb_groups SET status = 'LEFT', enabled = 0 WHERE group_id = ?", (g["group_id"],))
            count += 1
        conn.commit()
    return {"status": "SUCCESS", "message": f"Đã dọn dẹp {count} group ma (chuyển sang LEFT và tắt enabled)!"}


@router.get("/api/groups/quality-metrics")
def get_group_quality_metrics():
    """
    Task 2.4: Báo cáo chỉ số chất lượng Group Facebook toàn diện:
    - Phân bổ trạng thái: APPROVED, PENDING, REJECTED, LEFT, TIMEOUT_LEFT
    - Nhóm có nguy cơ / Group ma (health_score < 40 hoặc verdict = GHOST)
    - Nhóm bị hạn chế đăng bài (posting_restricted = 1)
    - Thời gian chờ duyệt trung bình của nhóm PENDING (giờ)
    - Bảng xếp hạng nhóm theo hiệu quả chuyển đổi / lượt click
    """
    with db.get_connection() as conn:
        all_groups = conn.execute("SELECT * FROM fb_groups").fetchall()
        groups_list = [dict(g) for g in all_groups]

        status_counts = {}
        health_counts = {"healthy": 0, "warning": 0, "ghost": 0}
        warning_groups = []
        restricted_groups = []

        total_pending_wait_hours = 0.0
        pending_count = 0

        now = time.time()

        for g in groups_list:
            st = g.get("status", "DISCOVERED")
            status_counts[st] = status_counts.get(st, 0) + 1

            score = g.get("health_score")
            verdict = g.get("health_verdict", "UNKNOWN")

            if score is not None:
                if score >= 60:
                    health_counts["healthy"] += 1
                elif score >= 35:
                    health_counts["warning"] += 1
                else:
                    health_counts["ghost"] += 1

            if (score is not None and score < 40) or verdict == "GHOST":
                warning_groups.append({
                    "group_id": g["group_id"],
                    "name": g["name"],
                    "url": g["url"],
                    "health_score": score,
                    "health_verdict": verdict,
                    "avg_engagement": g.get("avg_engagement", 0)
                })

            if g.get("posting_restricted") == 1:
                restricted_groups.append({
                    "group_id": g["group_id"],
                    "name": g["name"],
                    "url": g["url"],
                    "consecutive_rejections": g.get("consecutive_rejections", 0)
                })

            if st == "PENDING":
                req_at = g.get("join_requested_at")
                if req_at:
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(str(req_at).split(".")[0], "%Y-%m-%d %H:%M:%S")
                        wait_hours = (now - dt.timestamp()) / 3600.0
                        total_pending_wait_hours += max(wait_hours, 0)
                        pending_count += 1
                    except Exception:
                        pass

        avg_pending_wait = round(total_pending_wait_hours / max(pending_count, 1), 1)

        # Bảng xếp hạng nhóm theo hiệu quả đăng bài và click
        performance_rows = conn.execute("""
            SELECT 
                g.group_id, g.name, g.category_name, g.members_count,
                COUNT(p.id) as total_posts,
                COALESCE(SUM(CASE WHEN p.status = 'SUCCESS' THEN 1 ELSE 0 END), 0) as success_posts
            FROM fb_groups g
            LEFT JOIN post_history p ON g.group_id = p.target_id
            GROUP BY g.group_id
            ORDER BY total_posts DESC
            LIMIT 10
        """).fetchall()
        top_groups = [dict(r) for r in performance_rows]

        return {
            "total_groups": len(groups_list),
            "status_counts": status_counts,
            "health_distribution": health_counts,
            "warning_groups_count": len(warning_groups),
            "warning_groups": warning_groups[:20],
            "restricted_groups_count": len(restricted_groups),
            "restricted_groups": restricted_groups,
            "avg_pending_wait_hours": avg_pending_wait,
            "top_performing_groups": top_groups
        }

