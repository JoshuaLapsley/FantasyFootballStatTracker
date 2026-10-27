from yahoo_oauth import OAuth2

oauth = OAuth2(None, None, from_file='oauth2.json')

# simplest possible authenticated call
url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games?format=json"
resp = oauth.session.get(url)
print(resp.status_code)
print(resp.json())