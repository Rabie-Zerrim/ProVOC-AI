import requests
import os
from dotenv import load_dotenv
load_dotenv()

BASE = 'http://127.0.0.1:5000'
secret = os.getenv('BFF_SHARED_SECRET')

print('=== FINAL VERIFICATION TEST ===')

health = requests.get(f'{BASE}/health').json()
print(f'1. Health: {health}')

user1 = 'f217b69a-3aa9-4d44-a997-02442e2a6f30'
token = requests.post(
    f'{BASE}/api/auth/token/relay',
    json={'user_id': user1, 'display_name': 'Test'},
    headers={'X-BFF-Secret': secret}
).json().get('access_token')
print(f'2. Token: {"OK" if token else "FAIL"}')

headers = {'Authorization': f'Bearer {token}'}

recs = requests.get(f'{BASE}/api/recommendations', headers=headers)
print(f'3. Recommendations status: {recs.status_code}')
print(f'   Result: {recs.json()}')

start = requests.post(f'{BASE}/api/chat/start', json={
    'review_id': 'final-test-001',
    'transcript': 'The coffee was excellent and the staff were friendly',
    'listing_id': 'ChIJfinaltest',
    'language': 'en',
    'listing_context': {
        'business_name': 'Test Cafe',
        'networks': [],
        'context_note': 'Rating: 5 stars'
    },
    'previous_messages': []
}, headers=headers)
print(f'4. Chat start status: {start.status_code}')
session_id = start.json().get('session_id')

approve = requests.post(f'{BASE}/api/chat/approve',
    json={'session_id': session_id}, headers=headers)
print(f'5. Chat approve status: {approve.status_code}')
review = approve.json()
text = review.get('improved_text', review.get('review_text', ''))
print(f'   Review text: {text[:80]}')
print(f'   Rating: {review.get("rating")}')

recs2 = requests.get(f'{BASE}/api/recommendations', headers=headers)
print(f'6. Recommendations after new review: {recs2.json()}')

print('=== TEST COMPLETE ===')
