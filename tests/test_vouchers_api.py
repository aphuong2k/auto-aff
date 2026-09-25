import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("1. Testing GET /api/promotions/voucher-codes ...")
res = json.loads(urllib.request.urlopen('http://localhost:8000/api/promotions/voucher-codes').read())
print(f"✅ Vouchers count: {len(res['vouchers'])}")
for v in res['vouchers']:
    print(f"   • {v['code']}: {v['discount_desc']} (Type: {v['voucher_type']})")
print("\nCampaign Links:")
for k, v in res['campaign_links'].items():
    print(f"   🔗 {k}: {v}")

print("\n" + "="*80)
print("2. Testing GET /api/promotions/generated-posts ...")
posts = json.loads(urllib.request.urlopen('http://localhost:8000/api/promotions/generated-posts').read())
print("✅ Generated 4 real-world posts successfully!")

print("\n--- MẪU 1: BÀI MÃ NHẬP TAY (2 BƯỚC + LINK LIST) ---")
print(posts['post_manual_vouchers'])

print("\n--- MẪU 2: BÀI BÁO GIỜ BACK MÃ (2 BANNER + MẸO SĂN F5 / TIME.IS) ---")
print(posts['post_voucher_back_alert'])

print("\n--- MẪU 3: BÀI BẮN NHANH MÃ KHỦNG (25% 3TR, 25% 2.5TR) ---")
print(posts['post_flash_high_value'])

print("\n--- MẪU 4: BÀI DEAL ĐỒNG GIÁ 99K (MẸO BẬT/TẮT XU 0.1S) ---")
print(posts['post_flat_deal'])
