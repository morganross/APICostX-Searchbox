import os
from dotenv import load_dotenv
load_dotenv('/home/ubuntu/APICostX-Searchbox/.env')
for k, v in os.environ.items():
    if 'API_KEY' in k or 'PROVIDER' in k or 'DISABLED' in k:
        print(k, len(v))
