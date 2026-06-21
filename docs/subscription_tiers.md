# Subscription Tiers Implementation

## Database Schema
Add `subscriptionTier` property to Person nodes:
- `subscriptionTier`: "free" | "plus" (default: "free")
- `subscriptionSince`: datetime (when upgraded)
- `subscriptionExpires`: datetime (for time-limited plus)

## API Endpoints

### 1. GET /crm/subscription/{email}
Get current subscription status

### 2. POST /crm/subscription/upgrade
Upgrade to Plus tier
```json
{
  "email": "user@example.com",
  "tier": "plus",
  "durationMonths": 12
}
```

### 3. POST /crm/subscription/downgrade
Downgrade to Free tier

## Feature Gating

Middleware to check subscription tier:
```python
def require_plus_tier(func):
    def wrapper(*args, **kwargs):
        if user.subscriptionTier != "plus":
            raise HTTPException(403, "Plus tier required")
        return func(*args, **kwargs)
    return wrapper
```

## Frontend Components

### 1. Subscription Badge
Show tier on profile (Free = gray, Plus = gold)

### 2. Upgrade Modal
Payment/integration flow for upgrading

### 3. Feature Locked UI
Show "Plus only" badges on premium features

### 4. Tier Distribution Chart
Dashboard chart showing Free vs Plus users
