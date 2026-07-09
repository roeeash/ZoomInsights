.PHONY: build process local status done process-jira process-notify

build:
	docker compose build

# Process a cloud recording — interactive selection from recent recordings
# Usage: make process
# Optional: make process UUID=<uuid> to bypass interactive selection
process:
ifdef UUID
	docker compose run --rm zoom-insights $(UUID)
else
	bash docker/select-and-process.sh
endif

# Process the single MP4 in ./recordings/
# Usage: make local TITLE="My Meeting"
local:
	docker compose run --rm zoom-insights /recordings/meeting.mp4 --local --title "$(TITLE)"

# Show pending action items
status:
	docker compose run --rm zoom-insights status

# Mark a task done
# Usage: make done TASK=<task-id>
done:
	docker compose run --rm zoom-insights done --task-id $(TASK)

# Process with Jira export — interactive selection
# Usage: make process-jira
# Optional: make process-jira UUID=<uuid> to bypass interactive selection
process-jira:
ifdef UUID
	docker compose run --rm zoom-insights $(UUID) --jira
else
	bash docker/select-and-process.sh --jira
endif

# Process with Slack notification — interactive selection
# Usage: make process-notify WEBHOOK=<url>
# Optional: make process-notify UUID=<uuid> WEBHOOK=<url> to bypass interactive selection
process-notify:
ifdef UUID
	docker compose run --rm zoom-insights $(UUID) --notify $(WEBHOOK)
else
	bash docker/select-and-process.sh --notify $(WEBHOOK)
endif
