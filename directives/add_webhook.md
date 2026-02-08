# Directive: Add Webhook

> Create a new Modal webhook endpoint that executes a directive.

## Goal

Set up an event-driven webhook that triggers a specific directive when called.

## Inputs

- **slug**: URL-friendly identifier for the webhook (required)
- **directive_name**: Name of the directive file to execute (required)
- **description**: What this webhook does (required)
- **tools**: List of allowed tools for this webhook (required)

## Available Tools for Webhooks

- `send_email` - Send emails via configured SMTP
- `read_sheet` - Read data from Google Sheets
- `update_sheet` - Write data to Google Sheets

## Process

1. Create the directive file in `directives/` following the template
2. Add entry to `execution/webhooks.json`:
   ```json
   {
     "slug": "your-slug",
     "directive": "directive_name.md",
     "description": "What it does",
     "tools": ["send_email", "read_sheet"]
   }
   ```
3. Deploy to Modal: `modal deploy execution/modal_webhook.py`
4. Test the endpoint: `curl "https://nick-90891--claude-orchestrator-directive.modal.run?slug=your-slug"`

## Outputs

- New directive file in `directives/`
- Updated `execution/webhooks.json`
- Live webhook endpoint

## Endpoints Reference

- **List webhooks**: `https://nick-90891--claude-orchestrator-list-webhooks.modal.run`
- **Execute directive**: `https://nick-90891--claude-orchestrator-directive.modal.run?slug={slug}`
- **Test email**: `https://nick-90891--claude-orchestrator-test-email.modal.run`

## Edge Cases

- **Slug already exists**: Choose a different slug or update existing
- **Directive not found**: Ensure file exists in `directives/` with exact name
- **Tool not available**: Only use tools from the allowed list above

## Learnings

- All webhook activity streams to Slack in real-time
- Webhooks have scoped tool access for security
