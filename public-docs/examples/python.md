# Python Example

```python
import requests

payload = {
    "query": "lithium dendrite solid electrolyte interface",
    "max_results": 1,
}

response = requests.post("http://127.0.0.1:9000/search", json=payload, timeout=120)
response.raise_for_status()

context = response.json()["results"][0]["content"]
print(context[:2000])
```
