import requests

BASE = "http://127.0.0.1:8000"

# 1. register
r = requests.post(BASE + "/auth/register", json={
    "name": "Smoke Test",
    "email": "smoketest@example.com",
    "password": "testpass",
    "plan": "Free"
})
print('register', r.status_code, r.text)
if r.status_code not in (200, 400):
    raise SystemExit('register failed')
if r.status_code == 400 and 'Email already registered' not in r.text:
    raise SystemExit('register failed: ' + r.text)

# 2. token
r = requests.post(BASE + "/auth/token", data={"username": "smoketest@example.com", "password": "testpass"})
print('token', r.status_code, r.text)
if r.status_code != 200:
    raise SystemExit('token failed')
access = r.json().get('access_token')
headers = {"Authorization": f"Bearer {access}"}

# 3. upload campaign
data = {
    'template': 'Hello {{Name}}, {{CustomField}}',
    'campaign_name': 'Smoke'
}
with open('samples/contacts.csv', 'rb') as fh:
    files = {
        'file': ('contacts.csv', fh, 'text/csv')
    }
    res = requests.post(BASE + "/upload/campaign", headers=headers, files=files, data=data)
print('upload', res.status_code, res.text)
