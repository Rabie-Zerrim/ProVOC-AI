import os
import requests
from dotenv import load_dotenv

load_dotenv()

from taste_engine import TasteEngine

SEED_USER_1 = '11111111-1111-1111-1111-111111111111'
SEED_USER_2 = '22222222-2222-2222-2222-222222222222'
SEED_USER_3 = '33333333-3333-3333-3333-333333333333'
REAL_USER   = 'b009eaa2-fd6c-4b3e-bcf0-731ce237cf39'

# (user_id, business_name, business_id, review_text, rating, business_type)
REVIEWS = [
    # seed_user_1: Italian places only
    (SEED_USER_1, 'Prego - Menzah 5',        'ChIJI1Nw5mA1_RIRxgd2XCt7y18', 'Exceptional pasta and romantic atmosphere, great service',         5.0, 'restaurant italian'),
    (SEED_USER_1, 'Prego Mourouj 6',          'ChIJczgRcAA3_RIRcB5ECRokv_0', 'Best pizza in Tunis, crispy crust and very friendly staff',        5.0, 'restaurant italian'),
    (SEED_USER_1, 'Prego Fast Food',          'ChIJA9vsaTHL4hIRQmXO1QQm8eY', 'Quick tasty Italian food, excellent value for money',              4.0, 'restaurant italian fastfood'),
    (SEED_USER_1, 'Prego Lac Malaren',        'ChIJCV3bL4U1_RIRYUN1vy6Rny0', 'Elegant location by the lake, perfect tiramisu',                   5.0, 'restaurant italian'),

    # seed_user_2: Italian + coffee overlap
    (SEED_USER_2, 'Prego - Menzah 5',        'ChIJI1Nw5mA1_RIRxgd2XCt7y18', 'Love this place, pasta is incredible every time I visit',          5.0, 'restaurant italian'),
    (SEED_USER_2, 'Prego Mourouj 6',          'ChIJczgRcAA3_RIRcB5ECRokv_0', 'Great pizza and warm atmosphere, definitely coming back',          4.0, 'restaurant italian'),
    (SEED_USER_2, 'Cafe Culturel Biblio The', 'ChIJkcu5LBY1_RIRYx2l6sKk07w', 'Wonderful cultural vibe, amazing coffee selection',                4.0, 'cafe coffee'),
    (SEED_USER_2, 'Aura Cafe Tunis',          'ChIJkUPXSQA1_RIR0cIJxswW7hQ', 'Lovely ambiance, excellent espresso and pastries',                 5.0, 'cafe coffee'),

    # seed_user_3: Coffee places only
    (SEED_USER_3, 'Cafe Culturel Biblio The', 'ChIJkcu5LBY1_RIRYx2l6sKk07w', 'Perfect study spot, great coffee and cozy atmosphere',            5.0, 'cafe coffee'),
    (SEED_USER_3, 'Aura Cafe Tunis',          'ChIJkUPXSQA1_RIR0cIJxswW7hQ', 'Best espresso in Tunis, very stylish interior',                   5.0, 'cafe coffee'),
    (SEED_USER_3, 'Cafe Lounge Ksar Ayed',    'ChIJzV0jUAAz_RIRUj7i47P6CEs', 'Relaxing lounge vibe, excellent mint tea and coffee',             4.0, 'cafe coffee lounge'),
    (SEED_USER_3, 'Numa coffee kitchen',      'ChIJwe1SSfI1_RIR232XbIfbXNo', 'Great brunch menu, superb coffee and a nice kitchen feel',        5.0, 'cafe coffee kitchen'),

    # real account: one Italian taste signal
    (REAL_USER,   'Prego - Menzah 5',        'ChIJI1Nw5mA1_RIRxgd2XCt7y18', 'Amazing pasta and romantic atmosphere, highly recommend',          5.0, 'restaurant italian'),
]

engine = TasteEngine.get_instance()
engine._init()
if not engine._initialized:
    raise RuntimeError("TasteEngine failed to initialize - is Milvus running?")

print("Storing reviews...")
for user_id, business_name, business_id, review_text, rating, business_type in REVIEWS:
    ok = engine.store_review(
        user_id=user_id,
        business_id=business_id,
        business_name=business_name,
        review_text=review_text,
        rating=rating,
        business_type=business_type,
    )
    short_uid = user_id[:8]
    status = "OK  " if ok else "FAIL"
    print(f"  {status} | {short_uid}... | {business_name} ({business_id})")

print(f"\nStored {len(REVIEWS)} reviews total.")

# Fetch recommendations for the real account via HTTP
BASE   = 'http://127.0.0.1:5000'
secret = os.getenv('BFF_SHARED_SECRET')

token = requests.post(
    f'{BASE}/api/auth/token/relay',
    json={'user_id': REAL_USER, 'display_name': 'User'},
    headers={'X-BFF-Secret': secret},
).json().get('access_token')

recs = requests.get(
    f'{BASE}/api/recommendations',
    headers={'Authorization': f'Bearer {token}'},
).json()

print('\nRecommendations for real account (b009eaa2):')
for r in recs:
    print(f"  {r['business_name']:<30} | {r['business_id']:<30} | score={r['score']}")
