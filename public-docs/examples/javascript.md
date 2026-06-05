# JavaScript Example

```javascript
const response = await fetch("http://127.0.0.1:9000/search", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    query: "lithium dendrite solid electrolyte interface",
    max_results: 1
  })
});

if (!response.ok) throw new Error(`Searchbox failed: ${response.status}`);

const data = await response.json();
console.log(data.results[0].content.slice(0, 2000));
```
