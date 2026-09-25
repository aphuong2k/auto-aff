import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
url = 'http://localhost:8000/api/groups/with-matched-deals'
req = urllib.request.urlopen(url)
groups = json.loads(req.read().decode('utf-8'))

print(f"Tổng số nhóm: {len(groups)}")
print("=" * 80)
for g in groups[:12]:
    deal = g.get('matched_deal')
    deal_title = deal.get('name') if deal else '⚠️ KHÔNG CÓ DEAL NÀO (Hệ thống sẽ bỏ qua, không đăng ẩu)'
    deal_price = f"{deal.get('price_sale', 0):,}đ" if deal else ""
    deal_discount = f"-{deal.get('discount_percent', 0)}%" if deal else ""
    print(f"Nhóm: {g.get('name')[:35]:<35} | Ngành: {g.get('category_name')[:20]:<20} | Kho: {g.get('category_deals_count', 0):>2} deals")
    print(f"   ↳ Sản phẩm gán: {deal_title[:60]} {deal_price} {deal_discount}")
    print("-" * 80)
