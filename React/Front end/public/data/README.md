# CSV upload guidance

Sample files have been removed. Use these column names when preparing uploads:

## Network (people import)
Required:
- `email`, `first_name`, `last_name`

Optional:
- `gender`, `age`, `phone`, `address`, `lat`, `lon`, `supporter_type`
- `effort_hours`, `events_attended`, `tasks_completed`, `referral_count`
- `education`, `skills`, `time_availability`

## Survey & Consensus (dataset import)
Required:
- `conversation_id`, `participant_id`, `comment_id`, `comment_text`, `is_seed`, `vote`

Optional:
- `comment_created_at`, `reaction_created_at`, `participant_cluster`

Seed comments CSV:
- `comment_text`

## Due Diligence (watchlist import)
Required:
- `name`

Optional:
- `competitor_type`, `notes`
