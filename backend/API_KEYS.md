# API keys for pilot brands

These keys identify each brand when calling the sizing assistant. Remove or change a value to disable access instantly.

## Keys

| Brand  | API key             |
| ------ | ------------------- |
| Brand A| UN4TH-TEST-A1-BETA  |
| Brand B| UN4TH-TEST-B2-BETA  |
| Brand C| UN4TH-TEST-C3-BETA  |

## Usage

```
POST https://untold4th-backend.onrender.com/estimate
Headers:
  x-api-key: UN4TH-TEST-A1-BETA
Content-Type: multipart/form-data
Body:
  file: <customer_photo.jpg>
  user_height_cm: 170  # optional
```

Only the `/estimate` endpoint is gated; other routes remain unchanged.
