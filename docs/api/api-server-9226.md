# api-server-9226.py

## Purpose

Expose browser automation through a REST API.

## Responsibilities

- Launch Chrome
- Connect using CDP
- Load JavaScript scripts
- Execute browser automation
- Cache jobs
- Expose HTTP endpoints

## Dependencies

- cdpv116.py
- Flask
- scripts-library/unstop/
- Chrome

## Workflow

Client
↓

HTTP Request

↓

Flask

↓

Chrome Session Manager

↓

Chrome

↓

JavaScript

↓

JSON

## Endpoints

POST /api/init

POST /api/execute/get-job-list

POST /api/jobs/apply

GET /api/status

## Current Status

✅ Working

## Known Problems

- Flask port 5000 conflict

## Future Improvements

- Redis queue
- Persistent database
- Multiple Chrome sessions
