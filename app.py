import upstox_client
from upstox_client.rest import ApiException

api_instance = upstox_client.LoginApi()
api_version = '2.0'

try:
    # Set refresh_extended_token=True to get the extended token in response
    api_response = api_instance.token(
        api_version, 
        code='{your_auth_code}', 
        client_id='{your_client_id}', 
        client_secret='{your_client_secret}',
        redirect_uri='{your_redirect_url}', 
        grant_type='authorization_code',
        refresh_extended_token=True
    )
    print(f"Extended Token: {api_response.extended_token}")
except ApiException as e:
    print(f"Exception: {e}")
