import requests
import os
from dotenv import load_dotenv
load_dotenv()

BASE = 'http://127.0.0.1:5000'
secret = os.getenv('BFF_SHARED_SECRET')

user1 = 'f217b69a-3aa9-4d44-a997-02442e2a6f30'
user2 = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
user3 = 'b009eaa2-fd6c-4b3e-bcf0-731ce237cf39'

def get_token(uid):
    return requests.post(
        f'{BASE}/api/auth/token/relay',
        json={'user_id': uid, 'display_name': 'User'},
        headers={'X-BFF-Secret': secret}
    ).json().get('access_token')

def store_review(token, name, lid, transcript):
    start = requests.post(f'{BASE}/api/chat/start', json={
        'review_id': f'real-{lid}-{name[:5]}',
        'transcript': transcript,
        'listing_id': lid,
        'language': 'en',
        'listing_context': {'business_name': name, 'networks': [], 'context_note': 'Rating: 5'},
        'previous_messages': []
    }, headers={'Authorization': f'Bearer {token}'}).json()
    session_id = start.get('session_id')
    requests.post(f'{BASE}/api/chat/approve',
        json={'session_id': session_id}, headers={'Authorization': f'Bearer {token}'})
    print(f'Stored: {name} ({lid})')

real_places = [
    ('Prego - Menzah 5', 'ChIJI1Nw5mA1_RIRxgd2XCt7y18', 'Amazing pasta romantic atmosphere'),
    ('Prego Mourouj 6', 'ChIJczgRcAA3_RIRcB5ECRokv_0', 'Best pizza great service'),
    ('Prego Fast Food', 'ChIJA9vsaTHL4hIRQmXO1QQm8eY', 'Quick italian food good value'),
    ('Cafe Culturel Biblio The', 'ChIJkcu5LBY1_RIRYx2l6sKk07w', 'Cozy cafe great coffee'),
    ('Aura Cafe Tunis', 'ChIJkUPXSQA1_RIR0cIJxswW7hQ', 'Lovely ambiance excellent coffee'),
]

token1 = get_token(user1)
token2 = get_token(user2)

store_review(token1, real_places[0][0], real_places[0][1], real_places[0][2])
store_review(token1, real_places[3][0], real_places[3][1], real_places[3][2])

store_review(token2, real_places[0][0], real_places[0][1], 'Love this place pasta is amazing')
store_review(token2, real_places[1][0], real_places[1][1], real_places[1][2])
store_review(token2, real_places[4][0], real_places[4][1], real_places[4][2])

recs1 = requests.get(f'{BASE}/api/recommendations',
    headers={'Authorization': f'Bearer {token1}'}).json()
print('Recommendations for user1:', recs1)

token3 = get_token(user3)
recs3 = requests.get(f'{BASE}/api/recommendations',
    headers={'Authorization': f'Bearer {token3}'}).json()
print('Recommendations for user3 (real account):', recs3)
